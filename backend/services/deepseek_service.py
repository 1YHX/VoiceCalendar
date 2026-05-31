import json
import os
import re
from datetime import datetime, timedelta

import httpx
from dotenv import load_dotenv

from schemas import ParsedCommand


load_dotenv()

SYSTEM_PROMPT = """你是一个中文日历助手。请把用户的自然语言日程指令解析为严格 JSON。
当前时间由后端传入。
你需要识别创建、查询、删除日程提醒的指令。“显示日程”“列出日程”也属于查询。
如果用户表达的是修改或无法识别，请返回对应 intent，但不要执行创建。
必须只输出 JSON，不要 Markdown，不要解释。

输出格式：
{
"intent": "create | query | delete | update | unknown | need_clarification",
"title": "",
"description": "",
"start_time": "",
"end_time": "",
"reminder_minutes": 10,
"target_event_ids": [],
"confidence": 0.0,
"clarification_question": ""
}

规则：
1. 相对时间必须基于后端传入的当前时间解析。
2. 如果没有结束时间，默认持续 1 小时。
3. 如果没有提醒时间，默认提前 10 分钟。
4. 创建指令缺少具体时间时，返回 need_clarification。
5. 查询指令尽量解析查询日期；如果用户没有说日期，start_time 和 end_time 留空。
6. 查询“所有日程”“全部日程”时，title 必须留空，不要把“所有”或“全部”当作标题关键词。
7. 后端会传入已有日程列表。查询、删除、修改都必须结合已有日程理解用户真实目标。
8. 如果用户要查询或删除某些已有日程，并能从已有日程中判断目标，请把匹配日程 id 放入 target_event_ids。
9. 删除指令把要删除的事件关键词放到 title；如果同时有明确日期，也解析 start_time。
10. 只输出 JSON。"""


def _extract_json(content: str) -> dict:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _normalize_time(text: str) -> tuple[int, int] | None:
    # 未配置 DeepSeek key 时使用这个轻量兜底，保证演示指令仍能跑通。
    chinese_digits = {
        "零": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
        "十一": 11,
        "十二": 12,
    }
    match = re.search(r"(\d{1,2})点|([一二两三四五六七八九十]{1,2})点", text)
    if not match:
        return None
    hour = int(match.group(1)) if match.group(1) else chinese_digits.get(match.group(2))
    if hour is None:
        return None
    if ("下午" in text or "晚上" in text) and hour < 12:
        hour += 12
    minute = 30 if "点半" in text else 0
    return hour, minute


def _extract_title(text: str) -> str:
    title = re.sub(r"^.*?提醒我", "", text).strip()
    title = re.sub(r"(今天|明天|后天)?(上午|下午|晚上|中午|早上)?[一二两三四五六七八九十\d]{1,2}点(半)?", "", title)
    return title.strip(" ，。") or "未命名日程"


def _extract_action_keyword(text: str) -> str:
    keyword = re.sub(r"(帮我|请|一下|日程|提醒|提醒我|事件)", "", text)
    keyword = re.sub(r"(删除|取消|查看|查询|显示|列出|看看|有哪些|有什么)", "", keyword)
    keyword = re.sub(r"(今天|明天|后天)", "", keyword)
    keyword = re.sub(r"(今天|明天|后天)?(上午|下午|晚上|中午|早上)?[一二两三四五六七八九十\d]{1,2}点(半)?", "", keyword)
    return keyword.strip(" ，。") or ""


def _local_demo_parse(text: str, now: datetime) -> ParsedCommand:
    parsed_time = _normalize_time(text)
    if "删除" in text:
        return ParsedCommand(intent="delete", title=_extract_action_keyword(text), confidence=0.7)
    if any(word in text for word in ["查询", "查看", "显示", "列出"]):
        return ParsedCommand(intent="query", title=_extract_action_keyword(text), confidence=0.7)
    if "修改" in text or "改" in text:
        return ParsedCommand(intent="update", confidence=0.7)
    if "提醒我" not in text:
        return ParsedCommand(intent="unknown", confidence=0.3)
    if parsed_time is None:
        return ParsedCommand(
            intent="need_clarification",
            confidence=0.5,
            clarification_question="请补充具体时间。",
        )

    days = 0
    if "明天" in text:
        days = 1
    elif "后天" in text:
        days = 2
    hour, minute = parsed_time
    start = (now + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    return ParsedCommand(
        intent="create",
        title=_extract_title(text),
        start_time=start.strftime("%Y-%m-%d %H:%M:%S"),
        end_time=end.strftime("%Y-%m-%d %H:%M:%S"),
        reminder_minutes=10,
        confidence=0.8,
    )


async def parse_calendar_command(
    text: str,
    now: datetime | None = None,
    existing_events: list[dict] | None = None,
) -> ParsedCommand:
    now = now or datetime.now()
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key == "your_deepseek_api_key":
        return _local_demo_parse(text, now)

    # 真实解析交给 DeepSeek，要求模型只返回 JSON，后端再做结构化校验。
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "当前时间": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "用户指令": text,
                        "已有日程": existing_events or [],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return ParsedCommand(**_extract_json(content))
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 401:
            raise ValueError("DeepSeek 认证失败：请检查 DEEPSEEK_API_KEY 是否正确，并重启后端服务") from exc
        if status_code == 402:
            raise ValueError("DeepSeek 调用失败：账户余额不足或计费状态异常") from exc
        raise ValueError(f"DeepSeek 调用失败：HTTP {status_code}") from exc
    except Exception as exc:
        raise ValueError(f"DeepSeek 解析失败：{exc}") from exc


async def generate_reminder_text(event: dict, now: datetime | None = None) -> str:
    now = now or datetime.now()
    title = event.get("title", "日程")
    start_time = event.get("start_time", "")
    reminder_minutes = event.get("reminder_minutes", 10)
    fallback = f"日程提醒：{title} 即将开始，请注意时间安排。"

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key == "your_deepseek_api_key":
        return fallback

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是日历提醒播报助手。请生成一句自然、简短的中文语音提醒文案，只输出文案本身。",
            },
            {
                "role": "user",
                "content": (
                    f"当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"日程标题：{title}\n"
                    f"日程开始时间：{start_time}\n"
                    f"提前提醒分钟数：{reminder_minutes}\n"
                    "要求：不超过 35 个汉字，适合直接语音播报。"
                ),
            },
        ],
        "temperature": 0.4,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"].strip()
        return text.strip("` \n") or fallback
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 401:
            raise ValueError("DeepSeek 认证失败：请检查 DEEPSEEK_API_KEY 是否正确，并重启后端服务") from exc
        raise ValueError(f"DeepSeek 提醒文案生成失败：HTTP {status_code}") from exc
    except Exception as exc:
        raise ValueError(f"DeepSeek 提醒文案生成失败：{exc}") from exc


async def select_event_for_delete(command_text: str, events: list[dict]) -> dict:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key or api_key == "your_deepseek_api_key":
        return {"event_id": None, "confidence": 0.0, "reason": "DeepSeek 未配置"}
    if not events:
        return {"event_id": None, "confidence": 0.0, "reason": "没有候选日程"}

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是日程删除匹配助手。请根据用户删除指令，从候选日程里选择最应该删除的一条。"
                    "只能返回 JSON，不要解释。找不到明确匹配时 event_id 返回 null。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "用户删除指令": command_text,
                        "候选日程": events,
                        "输出格式": {
                            "event_id": "number|null",
                            "confidence": "0到1",
                            "reason": "简短原因",
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return _extract_json(content)
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 401:
            raise ValueError("DeepSeek 认证失败：请检查 DEEPSEEK_API_KEY 是否正确，并重启后端服务") from exc
        raise ValueError(f"DeepSeek 删除匹配失败：HTTP {status_code}") from exc
    except Exception as exc:
        raise ValueError(f"DeepSeek 删除匹配失败：{exc}") from exc
