"""
API endpoints for content generation (notes, quizzes, outlines).
"""

import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from uuid import UUID
import json
from datetime import datetime
from psycopg2.extras import Json

from app.models.content import (
    ContentGenerationRequest,
    OutlineResponse,
    NotesResponse,
    QuizResponse,
    CoverageReport,
    ComprehensiveMaterialsResponse,
    MaterialsStatusResponse
)
from app.services.content_generator import ContentGenerator, ContentGeneratorError
from app.services.database import DatabaseService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/content", tags=["content"])

# Initialize services
db = DatabaseService()


def _get_lecture_or_404(lecture_id: UUID):
    """Helper to get lecture and check it exists."""
    lecture = db.get_lecture(str(lecture_id))

    if not lecture:
        raise HTTPException(status_code=404, detail=f"Lecture {lecture_id} not found")

    if lecture['status'] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Lecture must be fully processed before generating materials (current status: {lecture['status']})"
        )

    return lecture


def _update_generation_status(
    lecture_id: UUID,
    status: str,
    progress: int,
    current_step: str = None,
    error_message: str = None
):
    """Update content generation status in database."""
    conn = db._get_conn()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO content_generation_status (lecture_id, status, progress_percent, current_step, error_message)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (lecture_id)
            DO UPDATE SET
                status = EXCLUDED.status,
                progress_percent = EXCLUDED.progress_percent,
                current_step = EXCLUDED.current_step,
                error_message = EXCLUDED.error_message,
                completed_at = CASE WHEN EXCLUDED.status IN ('completed', 'failed') THEN NOW() ELSE NULL END
        """, (str(lecture_id), status, progress, current_step, error_message))

        conn.commit()
        cursor.close()
    finally:
        db._put_conn(conn)


def _background_generate_materials(lecture_id: UUID, num_questions: int):
    """Background task to generate all materials."""
    try:
        _update_generation_status(lecture_id, "generating_outline", 10, "Extracting structured outline")

        generator = ContentGenerator()

        # Run full three-pass pipeline
        result = generator.generate_all(str(lecture_id), num_quiz_questions=num_questions, show_progress=True)

        # Store results in database
        _update_generation_status(lecture_id, "generating_outline", 30, "Saving outline")

        conn = db._get_conn()
        try:
            cursor = conn.cursor()

            # Store outline
            cursor.execute("""
                INSERT INTO lecture_outlines (lecture_id, outline, generated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (lecture_id) DO UPDATE SET
                    outline = EXCLUDED.outline,
                    generated_at = EXCLUDED.generated_at
            """, (str(lecture_id), Json(result["outline"]), datetime.now()))

            cursor.close()
        finally:
            db._put_conn(conn)

        # Store notes
        _update_generation_status(lecture_id, "generating_notes", 50, "Saving detailed notes")

        conn = db._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO lecture_notes (lecture_id, notes_markdown, generated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (lecture_id) DO UPDATE SET
                    notes_markdown = EXCLUDED.notes_markdown,
                    generated_at = EXCLUDED.generated_at
            """, (str(lecture_id), result["notes"], datetime.now()))

            cursor.close()
        finally:
            db._put_conn(conn)

        # Store quiz
        _update_generation_status(lecture_id, "generating_quiz", 70, "Saving quiz")

        conn = db._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO comprehensive_quizzes (lecture_id, quiz_data, num_questions, generated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (lecture_id) DO UPDATE SET
                    quiz_data = EXCLUDED.quiz_data,
                    num_questions = EXCLUDED.num_questions,
                    generated_at = EXCLUDED.generated_at
            """, (str(lecture_id), Json(result["quiz"]), len(result["quiz"]["questions"]), datetime.now()))

            cursor.close()
        finally:
            db._put_conn(conn)

        # Store coverage report
        _update_generation_status(lecture_id, "verifying", 90, "Saving coverage report")

        conn = db._get_conn()
        try:
            cursor = conn.cursor()
            coverage = result["coverage_report"]
            cursor.execute("""
                INSERT INTO coverage_reports (lecture_id, report, coverage_percent, quality_score, generated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (lecture_id) DO UPDATE SET
                    report = EXCLUDED.report,
                    coverage_percent = EXCLUDED.coverage_percent,
                    quality_score = EXCLUDED.quality_score,
                    generated_at = EXCLUDED.generated_at
            """, (
                str(lecture_id),
                Json(coverage),
                coverage["overall_assessment"]["coverage_percent"],
                coverage["overall_assessment"]["quality_score"],
                datetime.now()
            ))

            conn.commit()
            cursor.close()
        finally:
            db._put_conn(conn)

        _update_generation_status(lecture_id, "completed", 100, "All materials generated")
        logger.info(f"Successfully generated all materials for lecture {lecture_id}")

    except Exception as e:
        logger.error(f"Background content generation failed for {lecture_id}: {e}")
        _update_generation_status(lecture_id, "failed", 0, None, str(e))


@router.post("/lectures/{lecture_id}/generate", response_model=MaterialsStatusResponse)
async def generate_comprehensive_materials(
    lecture_id: UUID,
    request: ContentGenerationRequest,
    background_tasks: BackgroundTasks
):
    """
    Start generation of comprehensive materials (outline, notes, quiz) for a lecture.
    This runs in the background. Poll /status to check progress.
    """
    # Check lecture exists and is ready
    _get_lecture_or_404(lecture_id)

    # Initialize status
    _update_generation_status(lecture_id, "not_started", 0)

    # Start background task
    background_tasks.add_task(_background_generate_materials, lecture_id, request.num_quiz_questions)

    return MaterialsStatusResponse(
        lecture_id=lecture_id,
        status="not_started",
        progress_percent=0,
        current_step="Queued for processing"
    )


@router.get("/lectures/{lecture_id}/generation-status", response_model=MaterialsStatusResponse)
async def get_generation_status(lecture_id: UUID):
    """Get current status of materials generation."""
    conn = db._get_conn()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT status, progress_percent, current_step, error_message
            FROM content_generation_status
            WHERE lecture_id = %s
        """, (str(lecture_id),))

        result = cursor.fetchone()
        cursor.close()

        if not result:
            return MaterialsStatusResponse(
                lecture_id=lecture_id,
                status="not_started",
                progress_percent=0
            )

        return MaterialsStatusResponse(
            lecture_id=lecture_id,
            status=result[0],
            progress_percent=result[1],
            current_step=result[2],
            error_message=result[3]
        )
    finally:
        db._put_conn(conn)


@router.get("/lectures/{lecture_id}/notes", response_model=NotesResponse)
async def get_notes(lecture_id: UUID):
    """Get the generated detailed notes for a lecture."""
    conn = db._get_conn()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT notes_markdown, generated_at
            FROM lecture_notes
            WHERE lecture_id = %s
        """, (str(lecture_id),))

        result = cursor.fetchone()
        cursor.close()

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No notes found for lecture {lecture_id}. Generate materials first."
            )

        return NotesResponse(
            lecture_id=lecture_id,
            notes_markdown=result[0],
            generated_at=result[1]
        )
    finally:
        db._put_conn(conn)


@router.get("/lectures/{lecture_id}/comprehensive-quiz", response_model=QuizResponse)
async def get_comprehensive_quiz(lecture_id: UUID):
    """Get the comprehensive quiz for a lecture."""
    conn = db._get_conn()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT quiz_data, generated_at
            FROM comprehensive_quizzes
            WHERE lecture_id = %s
        """, (str(lecture_id),))

        result = cursor.fetchone()
        cursor.close()

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No quiz found for lecture {lecture_id}. Generate materials first."
            )

        quiz_data = result[0] if isinstance(result[0], dict) else json.loads(result[0])

        return QuizResponse(
            lecture_id=lecture_id,
            quiz_metadata=quiz_data.get("quiz_metadata", {}),
            questions=quiz_data.get("questions", []),
            generated_at=result[1]
        )
    finally:
        db._put_conn(conn)
