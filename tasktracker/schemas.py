from datetime import date
from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    name: str
    priority: int = Field(ge=1, le=5)
    duration: int = Field(ge=1, le=10)
    due_date: date | None = None
    scheduled_date: date | None = None


class TaskUpdate(BaseModel):
    name: str | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    duration: int | None = Field(default=None, ge=1, le=10)
    due_date: date | None = None
    scheduled_date: date | None = None
    completed: bool | None = None


# Each field has a None value which allows for partial updates omitting some fields
