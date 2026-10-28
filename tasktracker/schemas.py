from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    name: str
    priority: int = Field(ge=1, le=5)
    duration: int = Field(ge=1, le=10)
    due_date: date | None = None
    scheduled_date: date | None = None


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    duration: int | None = Field(default=None, ge=1, le=10)
    due_date: date | None = None
    scheduled_date: date | None = None


# Each field has a None value which allows for partial updates omitting some fields
