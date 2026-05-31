import re
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import get_db, init_db
from schemas import (
    AsrResponse,
    CommandRequest,
    CommandResponse,
    EventCreate,
    EventResponse,
    ReminderSpeechRequest,
    ReminderSpeechResponse,
    SpeechRequest,
)
from services.asr_service import recognize_audio
from services.calendar_service import (
    create_event,
    delete_event,
    list_events,
    list_events_for_day,
    parse_datetime,
    search_events,
)
from services.deepseek_service import (
    generate_reminder_text,
    parse_calendar_command,
    select_event_for_delete,
)
from services.text_normalizer import normalize_asr_text
from services.tts_service import synthesize_speech


app = FastAPI(title="VoiceCalendar API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/health")
def health():
    return {"success": True, "message": "ok"}


def _target_day_from_text(text: str, parsed_start_time: str = ""):
    today = datetime.now().date()
    if "今天" in text:
        return today
    if "明天" in text:
        return today + timedelta(days=1)
    if "后天" in text:
        return today + timedelta(days=2)
    if parsed_start_time:
        return parse_datetime(parsed_start_time).date()
    return None


def _command_keyword(text: str) -> str:
    keyword = re.sub(r"(帮我|请|一下|日程|提醒|提醒我|事件)", "", text)
    keyword = re.sub(r"(删除|取消|查看|查询|显示|列出|看看|有哪些|有什么)", "", keyword)
    keyword = re.sub(r"(今天|明天|后天)", "", keyword)
    keyword = re.sub(r"(今天|明天|后天)?(上午|下午|晚上|中午|早上)?[一二两三四五六七八九十\d]{1,2}点(半)?", "", keyword)
    keyword = keyword.strip(" ，。")
    return "" if _is_generic_query_keyword(keyword) else keyword


def _is_generic_query_keyword(keyword: str) -> bool:
    cleaned = re.sub(r"[的\s，。,.]", "", keyword)
    return cleaned in {
        "",
        "安排",
        "日程",
        "提醒",
        "事件",
        "所有",
        "全部",
        "所有日程",
        "全部日程",
        "所有安排",
        "全部安排",
        "所有提醒",
        "全部提醒",
    }


def _event_candidates(events):
    return [
        {
            "id": event.id,
            "title": event.title,
            "start_time": event.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": event.end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "raw_text": event.raw_text,
        }
        for event in events
    ]


@app.post("/api/command", response_model=CommandResponse)
async def command(payload: CommandRequest, db: Session = Depends(get_db)):
    command_text = normalize_asr_text(payload.text)
    all_events = list_events(db)
    event_context = _event_candidates(all_events)
    try:
        parsed = await parse_calendar_command(command_text, datetime.now(), event_context)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if parsed.intent == "query":
        target_ids = set(parsed.target_event_ids)
        if target_ids:
            results = [event for event in all_events if event.id in target_ids]
        else:
            target_day = _target_day_from_text(command_text, parsed.start_time)
            keyword = parsed.title.strip()
            if _is_generic_query_keyword(keyword):
                keyword = ""
            results = list_events_for_day(db, target_day) if target_day else all_events
            if keyword:
                results = [
                    event
                    for event in results
                    if keyword in event.title or keyword in event.raw_text
                ]
        return CommandResponse(
            success=True,
            message=f"找到 {len(results)} 条日程",
            parsed=parsed,
            events=results,
        )

    if parsed.intent == "delete":
        keyword = parsed.title or _command_keyword(command_text)
        if not all_events:
            return CommandResponse(success=False, message="没有找到可删除的日程", parsed=parsed)

        target = None
        target_ids = parsed.target_event_ids
        if target_ids:
            target = next((event for event in all_events if event.id == target_ids[0]), None)

        if target is None:
            try:
                selection = await select_event_for_delete(command_text, event_context)
            except ValueError:
                selection = {"event_id": None, "confidence": 0.0}
            selected_id = selection.get("event_id")
            confidence = float(selection.get("confidence") or 0)
            if selected_id and confidence >= 0.55:
                target = next((event for event in all_events if event.id == int(selected_id)), None)
            if target is None:
                candidates = search_events(db, keyword) if keyword else all_events
                target = candidates[0] if candidates else None

        if target is None:
            return CommandResponse(success=False, message="没有找到可删除的日程", parsed=parsed)

        if len(all_events) > 1 and not parsed.target_event_ids and not keyword:
            return CommandResponse(success=False, message="请说清楚要删除哪条日程", parsed=parsed)

        delete_event(db, target.id)
        return CommandResponse(success=True, message=f"已删除日程：{target.title}", parsed=parsed)

    if parsed.intent != "create":
        return CommandResponse(success=False, message="当前支持创建、查询、删除日程", parsed=parsed)
    if not parsed.title or not parsed.start_time or not parsed.end_time:
        return CommandResponse(success=False, message="解析结果缺少必要字段", parsed=parsed)

    try:
        event_data = EventCreate(
            title=parsed.title,
            description=parsed.description,
            start_time=parse_datetime(parsed.start_time),
            end_time=parse_datetime(parsed.end_time),
            reminder_minutes=parsed.reminder_minutes,
            raw_text=command_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"时间格式错误：{exc}") from exc

    event = create_event(db, event_data)
    return CommandResponse(success=True, message="日程创建成功", parsed=parsed, event=event)


@app.get("/api/events", response_model=list[EventResponse])
def events(db: Session = Depends(get_db)):
    return list_events(db)


@app.delete("/api/events/{event_id}")
def remove_event(event_id: int, db: Session = Depends(get_db)):
    if not delete_event(db, event_id):
        raise HTTPException(status_code=404, detail="日程不存在")
    return {"success": True, "message": "日程已删除"}


@app.post("/api/asr", response_model=AsrResponse)
async def asr(file: UploadFile = File(...)):
    file_bytes = await file.read()
    try:
        result = await recognize_audio(file_bytes, file.filename or "audio")
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if result.get("text"):
        result["text"] = normalize_asr_text(result["text"])
    if not result.get("success"):
        raise HTTPException(status_code=501, detail=result.get("message", "ASR 未启用"))
    return result


@app.post("/api/reminder-speech", response_model=ReminderSpeechResponse)
async def reminder_speech(payload: ReminderSpeechRequest):
    event_data = payload.event.model_dump()
    try:
        reminder_text = await generate_reminder_text(event_data, datetime.now())
        audio = await synthesize_speech(reminder_text)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ReminderSpeechResponse(success=True, text=reminder_text, **audio)


@app.post("/api/speech", response_model=ReminderSpeechResponse)
async def speech(payload: SpeechRequest):
    text = payload.text.strip()
    try:
        audio = await synthesize_speech(text)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ReminderSpeechResponse(success=True, text=text, **audio)
