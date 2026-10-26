from dataclasses import dataclass
from datetime import date


@dataclass
class Task:
    id: int
    name: str
    due_date: date | None
    priority: int
    duration: int
    completed: bool = False
