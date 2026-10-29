from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_serializer

from .validation import normalize_description


class TaskCreate(BaseModel):
    name: str
    priority: int = Field(ge=1, le=5)
    duration: int = Field(ge=1, le=10)
    due_date: date | None = None
    scheduled_date: date | None = None
    description: Annotated[str | None, AfterValidator(normalize_description)] = None


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    duration: int | None = Field(default=None, ge=1, le=10)
    due_date: date | None = None
    scheduled_date: date | None = None
    description: Annotated[str | None, AfterValidator(normalize_description)] = None


class TaskResponse(TaskCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    completed: bool

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        # Preserve the datetime format previously produced by dataclass responses.
        return value.isoformat()


# Each field has a None value which allows for partial updates omitting some fields
