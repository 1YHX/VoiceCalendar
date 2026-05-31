import re
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from models import Event
from schemas import EventCreate


TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
ACTION_WORDS_PATTERN = r"(提醒事项|日程安排|日程|提醒|事件|计划|安排)"


def parse_datetime(value: str) -> datetime:
    return datetime.strptime(value, TIME_FORMAT)


def create_event(db: Session, event_data: EventCreate) -> Event:
    event = Event(**event_data.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_events(db: Session) -> list[Event]:
    return db.query(Event).order_by(Event.start_time.asc()).all()


def list_events_for_day(db: Session, target_day: date) -> list[Event]:
    start = datetime.combine(target_day, time.min)
    end = start + timedelta(days=1)
    return (
        db.query(Event)
        .filter(Event.start_time >= start, Event.start_time < end)
        .order_by(Event.start_time.asc())
        .all()
    )


def normalize_search_text(value: str) -> str:
    text = re.sub(ACTION_WORDS_PATTERN, "", value or "")
    text = re.sub(r"[，。,.!！?？\s]", "", text)
    return text


def search_events(db: Session, keyword: str) -> list[Event]:
    cleaned = normalize_search_text(keyword)
    if not cleaned:
        return []
    events = db.query(Event).order_by(Event.start_time.asc()).all()
    return [
        event
        for event in events
        if cleaned in normalize_search_text(event.title)
        or cleaned in normalize_search_text(event.raw_text)
        or normalize_search_text(event.title) in cleaned
    ]


def delete_event(db: Session, event_id: int) -> bool:
    event = db.get(Event, event_id)
    if not event:
        return False
    db.delete(event)
    db.commit()
    return True
