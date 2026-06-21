from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from uuid import UUID


class StudyTask(BaseModel):
    id: UUID
    order_index: int
    title: str
    description: str
    done: bool


class StudyPlan(BaseModel):
    id: UUID
    lecture_id: UUID
    tasks: list[StudyTask]
    generated_at: datetime


class StudyTaskUpdate(BaseModel):
    done: bool
