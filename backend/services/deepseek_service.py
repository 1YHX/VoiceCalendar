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
你只需要处理创建日程的指令。
如果用户表达的是查询、删除、修改或无法识别，请返回对应 intent，但不要执行创建。
必须只输出 JSON，不要 Markdown，不要解释。

输出格式：
{
"intent": "create | query | delete | update | unknown | need_clarification",
"title": "",
"description": "",
"start_time": "",
"end_time": "",
"reminder_minutes": 10,
"confidence": 0.0,
"clarification_question": ""
}

规则：
1. 相对时间必须基于后端传入的当前时间解析。
2. 如果没有结束时间，默认持续 1 小时。
3. 如果没有提醒时间，默认提前 10 分钟。
4. 如果缺少具体时间，返回 need_clarification。
5. 只输出 JSON。"""


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


def _local_demo_parse(text: str, now: datetime) -> ParsedCommand:
    parsed_time = _normalize_time(text)
    if "删除" in text:
        return ParsedCommand(intent="delete", confidence=0.7)
    if "查询" in text or "查看" in text:
        return ParsedCommand(intent="query", confidence=0.7)
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


async def parse_calendar_command(text: str, now: datetime | None = None) -> ParsedCommand:
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
                "content": f"当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')}\n用户指令：{text}",
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
    except Exception as exc:
        raise ValueError(f"DeepSeek 解析失败：{exc}") from exc
