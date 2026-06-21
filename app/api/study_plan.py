import json
import logging
from fastapi import APIRouter, HTTPException

from app.models.study_plan import StudyPlan, StudyTask, StudyTaskUpdate
from app.services.database import DatabaseService, DatabaseError
from app.services.llm import LLMService, LLMError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["study-plan"])

db = DatabaseService()
llm = LLMService()


# ---------------------------------------------------------------------------
# POST /api/lectures/{lecture_id}/study-plan  — generate (or regenerate)
# ---------------------------------------------------------------------------

@router.post("/api/lectures/{lecture_id}/study-plan", response_model=StudyPlan)
async def generate_study_plan(lecture_id: str):
    """
    Generate (or regenerate) a study plan for a lecture.

    Uses the lecture outline when available; falls back to the cleaned
    transcript. Requires the lecture to have completed processing.
    """
    try:
        lecture = db.get_lecture(lecture_id)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")

    if lecture["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Lecture processing not complete (status: {lecture['status']})"
        )

    # Build content for the LLM: prefer outline, fall back to cleaned transcript
    try:
        outline = db.get_lecture_outline(lecture_id)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if outline:
        content = json.dumps(outline, ensure_ascii=False)
        logger.info(f"Generating study plan for {lecture_id} using outline")
    elif lecture.get("cleaned_transcript"):
        blocks = lecture["cleaned_transcript"]
        content = "\n\n".join(b.get("text", "") for b in blocks if b.get("text"))
        logger.info(f"Generating study plan for {lecture_id} using cleaned transcript")
    else:
        raise HTTPException(
            status_code=400,
            detail="No content available to generate a study plan (outline and transcript are both missing)"
        )

    # Generate tasks via LLM
    try:
        raw_tasks = llm.generate_study_plan(content)
    except LLMError as e:
        logger.error(f"LLM failed for study plan {lecture_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Study plan generation failed: {e}")

    # Persist
    try:
        plan_id = db.create_study_plan(lecture_id, raw_tasks)
        plan = db.get_study_plan(lecture_id)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return _plan_to_response(plan)


# ---------------------------------------------------------------------------
# GET /api/lectures/{lecture_id}/study-plan  — retrieve
# ---------------------------------------------------------------------------

@router.get("/api/lectures/{lecture_id}/study-plan", response_model=StudyPlan)
async def get_study_plan(lecture_id: str):
    """Return the study plan for a lecture. 404 if not yet generated."""
    try:
        lecture = db.get_lecture(lecture_id)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")

    try:
        plan = db.get_study_plan(lecture_id)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not plan:
        raise HTTPException(status_code=404, detail="Study plan not yet generated")

    return _plan_to_response(plan)


# ---------------------------------------------------------------------------
# PATCH /api/study-tasks/{task_id}  — mark done / undone
# ---------------------------------------------------------------------------

@router.patch("/api/study-tasks/{task_id}")
async def update_study_task(task_id: str, body: StudyTaskUpdate):
    """Toggle the done state of a single study task."""
    try:
        found = db.update_study_task(task_id, body.done)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not found:
        raise HTTPException(status_code=404, detail="Task not found")

    return {"task_id": task_id, "done": body.done}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _plan_to_response(plan: dict) -> StudyPlan:
    return StudyPlan(
        id=plan['id'],
        lecture_id=plan['lecture_id'],
        generated_at=plan['generated_at'],
        tasks=[
            StudyTask(
                id=t['id'],
                order_index=t['order_index'],
                title=t['title'],
                description=t['description'],
                done=t['done'],
            )
            for t in plan['tasks']
        ],
    )
