from typing import Optional, List, Literal
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request model for chat/Q&A endpoint."""
    question: str = Field(..., min_length=1, description="User's question")
    scope: Literal["global", "course", "lecture"] = Field(
        default="global",
        description="Search scope: global (all lectures), course (specific course), or lecture (specific lecture)"
    )
    scope_id: Optional[str] = Field(
        default=None,
        description="Course name (if scope=course) or lecture UUID (if scope=lecture)"
    )


class ChatSource(BaseModel):
    """Source chunk used in answer generation."""
    lecture_id: str = Field(..., description="UUID of the lecture")
    course_name: Optional[str] = Field(None, description="Course name (e.g., 'EIDI')")
    lecture_number: Optional[str] = Field(None, description="Lecture number")
    timestamp: str = Field(..., description="Timestamp in HH:MM:SS format")
    timestamp_seconds: int = Field(..., description="Timestamp in seconds")
    chunk_text: str = Field(..., description="Excerpt from the chunk")
    similarity: float = Field(..., description="Similarity score (0-1)")
    relevance_score: Optional[float] = Field(None, description="LLM relevance score (0-10) if re-ranking was used")


class ChatResponse(BaseModel):
    """Response model for chat/Q&A endpoint."""
    answer: str = Field(..., description="LLM-generated answer")
    sources: List[ChatSource] = Field(..., description="Source chunks used to generate answer")
    question: str = Field(..., description="Original question")
    scope: str = Field(..., description="Search scope used")
    optimized_query: Optional[str] = Field(None, description="Preprocessed query used for retrieval (if query preprocessing enabled)")
