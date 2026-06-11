"""
Pydantic models for content generation (notes, quizzes, outlines).
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from uuid import UUID


class ContentGenerationRequest(BaseModel):
    """Request to generate comprehensive materials for a lecture."""
    num_quiz_questions: int = Field(default=20, ge=5, le=50)


class OutlineResponse(BaseModel):
    """Response containing the extracted lecture outline."""
    lecture_id: UUID
    outline: Dict[str, Any]
    generated_at: datetime


class NotesResponse(BaseModel):
    """Response containing the generated detailed notes."""
    lecture_id: UUID
    notes_markdown: str
    generated_at: datetime


class QuizQuestion(BaseModel):
    """Single quiz question model."""
    question_id: int
    type: str  # "multiple_choice", "true_false", "short_answer"
    difficulty: str  # "basic", "intermediate", "advanced"
    topic: str
    question_text: str
    options: Optional[List[Dict[str, str]]] = None  # For multiple choice
    correct_answer: str
    explanation: str
    source_reference: Optional[str] = None


class QuizResponse(BaseModel):
    """Response containing the generated quiz."""
    lecture_id: UUID
    quiz_metadata: Dict[str, Any]
    questions: List[QuizQuestion]
    generated_at: datetime


class CoverageReport(BaseModel):
    """Coverage verification report."""
    lecture_id: UUID
    coverage_summary: Dict[str, Any]
    notes_coverage: Dict[str, Any]
    quiz_coverage: Dict[str, Any]
    gaps: List[Dict[str, Any]]
    quality_issues: List[Dict[str, Any]]
    overall_assessment: Dict[str, Any]
    generated_at: datetime


class ComprehensiveMaterialsResponse(BaseModel):
    """Complete response with all generated materials."""
    lecture_id: UUID
    outline: Dict[str, Any]
    notes_markdown: str
    quiz: QuizResponse
    coverage_report: CoverageReport
    generated_at: datetime


class MaterialsStatusResponse(BaseModel):
    """Status of materials generation process."""
    lecture_id: UUID
    status: str  # "not_started", "generating_outline", "generating_notes", "generating_quiz", "verifying", "completed", "failed"
    progress_percent: int
    current_step: Optional[str] = None
    error_message: Optional[str] = None
