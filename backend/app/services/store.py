"""Task persistence. SQLite by default; set DATABASE_URL to a PostgreSQL URL for Postgres."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import Column, DateTime, String, Text, create_engine, select
from sqlalchemy.orm import declarative_base, sessionmaker

from ..config import get_settings

Base = declarative_base()


def _now():
    return datetime.now(timezone.utc)


class TaskRow(Base):
    __tablename__ = "tasks"
    id = Column(String(36), primary_key=True)
    owner = Column(String(32), index=True, nullable=False)
    repository_url = Column(String(300), nullable=False)
    task_text = Column(Text, nullable=False)
    status = Column(String(24), nullable=False, default="queued")
    error = Column(Text, default="")
    state_json = Column(Text, default="{}")
    events_json = Column(Text, default="[]")
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


@lru_cache(maxsize=4)
def _session_factory(url: str):
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    engine = create_engine(url, **kwargs)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _session():
    return _session_factory(get_settings().database_url)()


def create_task(owner: str, repository_url: str, task: str) -> str:
    task_id = str(uuid.uuid4())
    with _session() as s:
        s.add(TaskRow(id=task_id, owner=owner, repository_url=repository_url, task_text=task))
        s.commit()
    return task_id


def get_task(task_id: str, owner: str | None = None) -> TaskRow | None:
    with _session() as s:
        row = s.get(TaskRow, task_id)
        return row if row and (owner is None or row.owner == owner) else None


def list_tasks(owner: str, limit: int = 30) -> list[TaskRow]:
    with _session() as s:
        return list(s.scalars(select(TaskRow).where(TaskRow.owner == owner).order_by(TaskRow.created_at.desc()).limit(limit)))


def update_task(task_id: str, *, status: str | None = None, error: str | None = None, state: dict | None = None) -> None:
    with _session() as s:
        row = s.get(TaskRow, task_id)
        if not row:
            return
        if status is not None:
            row.status = status
        if error is not None:
            row.error = error
        if state is not None:
            row.state_json = json.dumps(state)
        s.commit()


def append_event(task_id: str, step: str, status: str, message: str, kind: str) -> None:
    with _session() as s:
        row = s.get(TaskRow, task_id)
        if not row:
            return
        events = json.loads(row.events_json or "[]")
        events.append({"t": _now().isoformat(), "step": step, "status": status, "message": message[:400], "kind": kind})
        row.events_json = json.dumps(events)
        s.commit()


def load_state(row: TaskRow) -> dict:
    return json.loads(row.state_json or "{}")


def load_events(row: TaskRow) -> list[dict]:
    return json.loads(row.events_json or "[]")
