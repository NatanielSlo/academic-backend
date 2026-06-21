from datetime import date as DateType, datetime
from typing import Optional
from pydantic import BaseModel, HttpUrl, Field
from uuid import UUID, uuid4


class LectureCreate(BaseModel):
    """Request model for creating a new lecture."""
    url: str
    course_name: Optional[str] = None
    lecture_number: Optional[str] = None
    date: Optional[DateType] = None


class LectureResponse(BaseModel):
    """Response model after lecture creation."""
    lecture_id: UUID
    status: str
    course_name: Optional[str] = None
    lecture_number: Optional[str] = None
    date: Optional[DateType] = None


class LectureStatus(BaseModel):
    """Response model for lecture processing status."""
    lecture_id: UUID
    status: str  # 'downloading', 'transcribing', 'embedding', 'completed', 'failed'
    progress_percent: int
    error_message: Optional[str] = None


class LectureListItem(BaseModel):
    """Single lecture item in list response."""
    id: UUID
    url: str
    course_name: Optional[str]
    lecture_number: Optional[str]
    date: Optional[DateType]
    status: str
    created_at: datetime


class LectureList(BaseModel):
    """Response model for lecture list."""
    lectures: list[LectureListItem]
