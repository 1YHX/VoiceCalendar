from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from models import Event
from schemas import EventCreate


TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


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


def search_events(db: Session, keyword: str) -> list[Event]:
    cleaned = keyword.strip()
    if not cleaned:
        return []
    return (
        db.query(Event)
        .filter((Event.title.contains(cleaned)) | (Event.raw_text.contains(cleaned)))
        .order_by(Event.start_time.asc())
        .all()
    )


def delete_event(db: Session, event_id: int) -> bool:
    event = db.get(Event, event_id)
    if not event:
        return False
    db.delete(event)
    db.commit()
    return True
