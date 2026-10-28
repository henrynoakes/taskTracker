from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class Task:
    id: int
    name: str
    priority: int
    duration: int
    created_at: datetime
    due_date: date | None = None
    completed: bool = False
    scheduled_date: date | None = None


@dataclass
class WorkLogEntry:
    id: int
    task_id: int | None
    task_name: str
    work_date: date
    recorded_at: datetime
    duration: int
