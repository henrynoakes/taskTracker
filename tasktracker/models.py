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
