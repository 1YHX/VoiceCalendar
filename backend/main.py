from datetime import datetime

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import get_db, init_db
from schemas import AsrResponse, CommandRequest, CommandResponse, EventCreate, EventResponse
from services.asr_service import recognize_audio
from services.calendar_service import create_event, delete_event, list_events, parse_datetime
from services.deepseek_service import parse_calendar_command


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


@app.post("/api/command", response_model=CommandResponse)
async def command(payload: CommandRequest, db: Session = Depends(get_db)):
    try:
        parsed = await parse_calendar_command(payload.text, datetime.now())
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if parsed.intent != "create":
        return CommandResponse(success=False, message="当前 MVP 只支持创建日程", parsed=parsed)
    if not parsed.title or not parsed.start_time or not parsed.end_time:
        return CommandResponse(success=False, message="解析结果缺少必要字段", parsed=parsed)

    try:
        event_data = EventCreate(
            title=parsed.title,
            description=parsed.description,
            start_time=parse_datetime(parsed.start_time),
            end_time=parse_datetime(parsed.end_time),
            reminder_minutes=parsed.reminder_minutes,
            raw_text=payload.text,
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
    if not result.get("success"):
        raise HTTPException(status_code=501, detail=result.get("message", "ASR 未启用"))
    return result
