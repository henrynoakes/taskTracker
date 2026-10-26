from dataclasses import dataclass, field
from datetime import UTC, date, datetime


@dataclass
class Task:
    id: int
    name: str
    priority: int
    duration: int
    due_date: date | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed: bool = False
