"""
API endpoints for content generation (notes, quizzes, outlines).
"""

import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from uuid import UUID
from typing import Optional
import json
from datetime import datetime
from psycopg2.extras import Json

from app.models.content import (
    ContentGenerationRequest,
    OutlineResponse,
    NotesResponse,
    NoteTranslationRequest,
    NoteTranslationResponse,
    QuizResponse,
    QuizAttemptRequest,
    QuizAttemptResponse,
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


def _load_notes_markdown(lecture_id: str) -> Optional[str]:
    """Return the stored (German) notes Markdown for a lecture, or None if not generated yet."""
    conn = db._get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT notes_markdown FROM lecture_notes WHERE lecture_id = %s", (lecture_id,))
        row = cursor.fetchone()
        cursor.close()
        return row[0] if row else None
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
        # Store the full quiz (metadata + questions) as a new row in `quizzes`. Each
        # generation adds a row, so previously generated quizzes and their attempts are
        # preserved; the API serves the most recent one per lecture.
        quiz_id = db.create_quiz(lid, quiz)
        logger.info(f"Saved quiz {quiz_id} for lecture {lecture_id}")

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


@router.post("/lectures/{lecture_id}/notes/translate", response_model=NoteTranslationResponse)
async def translate_notes(lecture_id: UUID, request: NoteTranslationRequest):
    """
    Translate a lecture's German notes into Polish or English and persist the result.

    Requires notes to have been generated first (POST /generate-notes). Translation uses
    the cheap/fast DeepSeek model. Re-running overwrites the stored translation for that
    language (UPSERT on lecture_id + language).
    """
    lang_code = ContentGenerator.normalize_language(request.language)
    if not lang_code:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language {request.language!r}. Use 'pl'/'polish' or 'en'/'english'.",
        )

    german_notes = _load_notes_markdown(str(lecture_id))
    if not german_notes:
        raise HTTPException(
            status_code=404,
            detail=f"No notes found for lecture {lecture_id}. Generate notes first.",
        )

    generator = ContentGenerator()
    try:
        translated = generator.translate_notes(german_notes, lang_code)
    except ContentGeneratorError as e:
        logger.error(f"Notes translation failed for {lecture_id} -> {lang_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    generated_at = datetime.now()
    _save_artifact(
        """
        INSERT INTO lecture_note_translations (lecture_id, language, notes_markdown, source_language, generated_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (lecture_id, language) DO UPDATE SET
            notes_markdown = EXCLUDED.notes_markdown,
            source_language = EXCLUDED.source_language,
            generated_at = EXCLUDED.generated_at
        """,
        (str(lecture_id), lang_code, translated, "de", generated_at),
    )
    logger.info(f"Translated notes for lecture {lecture_id} -> {lang_code}")

    return NoteTranslationResponse(
        lecture_id=lecture_id,
        language=lang_code,
        notes_markdown=translated,
        generated_at=generated_at,
    )


@router.get("/lectures/{lecture_id}/notes/translation", response_model=NoteTranslationResponse)
async def get_note_translation(lecture_id: UUID, language: str):
    """Get a previously generated note translation (?language=pl or ?language=en)."""
    lang_code = ContentGenerator.normalize_language(language)
    if not lang_code:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language {language!r}. Use 'pl'/'polish' or 'en'/'english'.",
        )

    conn = db._get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT notes_markdown, generated_at
            FROM lecture_note_translations
            WHERE lecture_id = %s AND language = %s
        """, (str(lecture_id), lang_code))
        result = cursor.fetchone()
        cursor.close()

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No {lang_code} translation found for lecture {lecture_id}. Translate notes first.",
            )

        return NoteTranslationResponse(
            lecture_id=lecture_id,
            language=lang_code,
            notes_markdown=result[0],
            generated_at=result[1],
        )
    finally:
        db._put_conn(conn)


def _unpack_quiz(stored: Any) -> tuple[list, dict]:
    """Normalize a stored quiz `questions` column into (questions, quiz_metadata).

    Handles both shapes: the full quiz object ({quiz_metadata, questions, ...}) and a
    bare list of questions (rebuilds metadata from the questions in that case)."""
    if isinstance(stored, str):
        stored = json.loads(stored)

    if isinstance(stored, dict):
        questions = stored.get("questions", []) or []
        metadata = stored.get("quiz_metadata") or {}
    else:
        questions = stored or []
        metadata = {}

    if not metadata:
        difficulty = {"basic": 0, "intermediate": 0, "advanced": 0}
        for q in questions:
            d = q.get("difficulty")
            if d in difficulty:
                difficulty[d] += 1
        metadata = {
            "total_questions": len(questions),
            "topics_covered": sorted({q.get("topic", "") for q in questions if q.get("topic")}),
            "difficulty_distribution": difficulty,
        }
    return questions, metadata


@router.get("/lectures/{lecture_id}/comprehensive-quiz", response_model=QuizResponse)
async def get_comprehensive_quiz(lecture_id: UUID):
    """Get the most recently generated quiz for a lecture (from the `quizzes` table)."""
    conn = db._get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, questions, created_at
            FROM quizzes
            WHERE lecture_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (str(lecture_id),))
        result = cursor.fetchone()
        cursor.close()

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No quiz found for lecture {lecture_id}. Generate materials first."
            )

        quiz_id, stored, created_at = result
        questions, metadata = _unpack_quiz(stored)

        return QuizResponse(
            lecture_id=lecture_id,
            quiz_id=quiz_id,
            quiz_metadata=metadata,
            questions=questions,
            generated_at=created_at,
        )
    finally:
        db._put_conn(conn)


@router.post("/quizzes/{quiz_id}/attempts", response_model=QuizAttemptResponse)
async def submit_quiz_attempt(quiz_id: UUID, attempt: QuizAttemptRequest):
    """
    Save a quiz attempt to `quiz_attempts`.

    `score` may be fractional (open-ended questions can earn partial credit via the
    learner's self-grade); it is rounded for the INTEGER column. The full answer map and
    self-grades are preserved in the JSONB `answers` column for exact reconstruction.
    """
    if not db.get_quiz(str(quiz_id)):
        raise HTTPException(status_code=404, detail=f"Quiz {quiz_id} not found")

    if attempt.score > attempt.total:
        raise HTTPException(status_code=400, detail="score cannot exceed total")

    answers_payload = {
        "answers": attempt.answers,
        "self_grades": attempt.self_grades or {},
    }
    attempt_id = db.save_quiz_attempt(
        quiz_id=str(quiz_id),
        score=round(attempt.score),
        total=attempt.total,
        answers=answers_payload,
    )

    return QuizAttemptResponse(
        attempt_id=attempt_id,
        quiz_id=quiz_id,
        score=round(attempt.score),
        total=attempt.total,
        submitted_at=datetime.now(),
    )


@router.get("/lectures/{lecture_id}/quizzes")
async def list_lecture_quizzes(lecture_id: UUID):
    """List all quizzes generated for a lecture (newest first), with attempt stats.

    Powers the "Old Quizzes" view, where a learner can retake any previously generated
    quiz. `best_score` is omitted when there are no attempts yet.
    """
    conn = db._get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT q.id, q.questions, q.created_at,
                   COUNT(a.id) AS attempts_count,
                   MAX(a.score) AS best_score
            FROM quizzes q
            LEFT JOIN quiz_attempts a ON a.quiz_id = q.id
            WHERE q.lecture_id = %s
            GROUP BY q.id, q.questions, q.created_at
            ORDER BY q.created_at DESC
        """, (str(lecture_id),))
        rows = cursor.fetchall()
        cursor.close()

        quizzes = []
        for row in rows:
            questions, _ = _unpack_quiz(row[1])
            item = {
                "id": str(row[0]),
                "lecture_id": str(lecture_id),
                "created_at": row[2],
                "questions_count": len(questions),
                "attempts_count": row[3],
            }
            if row[4] is not None:
                item["best_score"] = row[4]
            quizzes.append(item)
        return {"quizzes": quizzes}
    finally:
        db._put_conn(conn)


@router.get("/quizzes/{quiz_id}", response_model=QuizResponse)
async def get_quiz_by_id(quiz_id: UUID):
    """Fetch a single quiz by id (used to retake a specific past quiz)."""
    quiz = db.get_quiz(str(quiz_id))
    if not quiz:
        raise HTTPException(status_code=404, detail=f"Quiz {quiz_id} not found")

    questions, metadata = _unpack_quiz(quiz["questions"])
    return QuizResponse(
        lecture_id=quiz["lecture_id"],
        quiz_id=quiz["id"],
        quiz_metadata=metadata,
        questions=questions,
        generated_at=quiz["created_at"],
    )


@router.get("/quizzes/{quiz_id}/attempts")
async def list_quiz_attempts(quiz_id: UUID):
    """List saved attempts for a quiz, most recent first."""
    conn = db._get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, score, total, answers, completed_at
            FROM quiz_attempts
            WHERE quiz_id = %s
            ORDER BY completed_at DESC
        """, (str(quiz_id),))
        rows = cursor.fetchall()
        cursor.close()

        attempts = []
        for row in rows:
            stored = row[3] if isinstance(row[3], dict) else json.loads(row[3])
            attempts.append({
                "attempt_id": str(row[0]),
                "score": row[1],
                "total": row[2],
                "answers": stored.get("answers", stored),
                "self_grades": stored.get("self_grades", {}),
                "submitted_at": row[4],
            })
        return {"quiz_id": str(quiz_id), "attempts": attempts}
    finally:
        db._put_conn(conn)
