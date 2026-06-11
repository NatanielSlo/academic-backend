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


def _save_artifact(sql: str, params: tuple):
    """Run a single INSERT/UPSERT and commit it on its own connection."""
    conn = db._get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        cursor.close()
    finally:
        db._put_conn(conn)


def _load_outline(lecture_id: str):
    """Return the stored outline for a lecture, or None if it hasn't been generated yet."""
    conn = db._get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT outline FROM lecture_outlines WHERE lecture_id = %s", (lecture_id,))
        row = cursor.fetchone()
        cursor.close()
        if not row:
            return None
        return row[0] if isinstance(row[0], dict) else json.loads(row[0])
    finally:
        db._put_conn(conn)


def _ensure_outline(generator: ContentGenerator, lecture_id: UUID) -> dict:
    """
    Notes and quiz both depend on the outline (Pass 1). Reuse the stored outline if
    present; otherwise generate and persist it once so the second artifact is cheap.
    """
    lid = str(lecture_id)
    existing = _load_outline(lid)
    if existing:
        return existing

    _update_generation_status(lecture_id, "generating_outline", 20, "Extracting structured outline")
    transcript = generator.get_transcript_text(lid)
    outline = generator.pass1_extract_outline(lid, transcript)
    _save_artifact(
        """
        INSERT INTO lecture_outlines (lecture_id, outline, generated_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (lecture_id) DO UPDATE SET
            outline = EXCLUDED.outline, generated_at = EXCLUDED.generated_at
        """,
        (lid, Json(outline), datetime.now()),
    )
    return outline


def _background_generate_notes(lecture_id: UUID):
    """Background task: ensure outline exists, then generate and persist notes."""
    lid = str(lecture_id)
    generator = ContentGenerator()
    try:
        outline = _ensure_outline(generator, lecture_id)

        _update_generation_status(lecture_id, "generating_notes", 60, "Generating detailed notes")
        notes = generator.pass2_generate_notes(lid, outline)
        _save_artifact(
            """
            INSERT INTO lecture_notes (lecture_id, notes_markdown, generated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (lecture_id) DO UPDATE SET
                notes_markdown = EXCLUDED.notes_markdown, generated_at = EXCLUDED.generated_at
            """,
            (lid, notes, datetime.now()),
        )

        _update_generation_status(lecture_id, "completed", 100, "Notes generated")
        logger.info(f"Successfully generated notes for lecture {lecture_id}")
    except Exception as e:
        logger.error(f"Background notes generation failed for {lecture_id}: {e}")
        _update_generation_status(lecture_id, "failed", 0, None, str(e))


def _background_generate_quiz(lecture_id: UUID, num_questions: int):
    """Background task: ensure outline exists, then generate and persist the quiz."""
    lid = str(lecture_id)
    generator = ContentGenerator()
    try:
        outline = _ensure_outline(generator, lecture_id)

        _update_generation_status(lecture_id, "generating_quiz", 60, "Generating quiz")
        quiz = generator.pass2_generate_quiz(lid, outline, num_questions=num_questions)
        _save_artifact(
            """
            INSERT INTO comprehensive_quizzes (lecture_id, quiz_data, num_questions, generated_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (lecture_id) DO UPDATE SET
                quiz_data = EXCLUDED.quiz_data, num_questions = EXCLUDED.num_questions,
                generated_at = EXCLUDED.generated_at
            """,
            (lid, Json(quiz), len(quiz.get("questions", [])), datetime.now()),
        )

        _update_generation_status(lecture_id, "completed", 100, "Quiz generated")
        logger.info(f"Successfully generated quiz for lecture {lecture_id}")
    except Exception as e:
        logger.error(f"Background quiz generation failed for {lecture_id}: {e}")
        _update_generation_status(lecture_id, "failed", 0, None, str(e))


@router.post("/lectures/{lecture_id}/generate-notes", response_model=MaterialsStatusResponse)
async def generate_notes(
    lecture_id: UUID,
    background_tasks: BackgroundTasks,
):
    """
    Start generation of detailed notes for a lecture (generates the outline first if
    it doesn't exist yet). Runs in the background; poll /generation-status for progress.
    """
    _get_lecture_or_404(lecture_id)
    _update_generation_status(lecture_id, "not_started", 0, "Queued: notes")
    background_tasks.add_task(_background_generate_notes, lecture_id)
    return MaterialsStatusResponse(
        lecture_id=lecture_id,
        status="not_started",
        progress_percent=0,
        current_step="Queued for processing (notes)",
    )


@router.post("/lectures/{lecture_id}/generate-quiz", response_model=MaterialsStatusResponse)
async def generate_quiz(
    lecture_id: UUID,
    request: ContentGenerationRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start generation of the comprehensive quiz for a lecture (generates the outline
    first if it doesn't exist yet). Runs in the background; poll /generation-status.
    """
    _get_lecture_or_404(lecture_id)
    _update_generation_status(lecture_id, "not_started", 0, "Queued: quiz")
    background_tasks.add_task(_background_generate_quiz, lecture_id, request.num_quiz_questions)
    return MaterialsStatusResponse(
        lecture_id=lecture_id,
        status="not_started",
        progress_percent=0,
        current_step="Queued for processing (quiz)",
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
