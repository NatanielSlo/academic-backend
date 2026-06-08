from fastapi import APIRouter, BackgroundTasks, HTTPException
from uuid import uuid4
import logging
from pathlib import Path

from app.models.lecture import LectureCreate, LectureResponse
from app.services.audio_extractor import AudioExtractor, AudioExtractionError
from app.services.transcription import TranscriptionService, TranscriptionError
from app.services.chunker import TextChunker, ChunkingError
from app.services.embeddings import EmbeddingService, EmbeddingError
from app.services.database import DatabaseService, DatabaseError
from app.services.llm import LLMService, LLMError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lectures", tags=["lectures"])

# Initialize services
db = DatabaseService()
audio_extractor = AudioExtractor()
transcription_service = TranscriptionService()
chunker = TextChunker()
embedding_service = EmbeddingService()
llm_service = LLMService()


def process_lecture_background(lecture_id: str, url: str):
    """
    Background task for full lecture processing pipeline:
    1. Download audio (MP3)
    2. Transcribe with Whisper (chunked for large files)
    3. Chunk transcript into token-sized segments
    4. Generate embeddings
    5. Store everything in database
    """
    try:
        # ==================== STEP 1: Download Audio ====================
        logger.info(f"[{lecture_id}] Step 1/5: Downloading audio")
        db.update_lecture_status(lecture_id, "downloading", progress_percent=10)

        audio_path = audio_extractor.extract_audio(url, lecture_id)
        db.update_lecture_audio_path(lecture_id, str(audio_path))

        logger.info(f"[{lecture_id}] Audio downloaded: {audio_path}")
        db.update_lecture_status(lecture_id, "downloading", progress_percent=20)

        # ==================== STEP 2: Transcribe Audio ====================
        logger.info(f"[{lecture_id}] Step 2/6: Transcribing audio")
        db.update_lecture_status(lecture_id, "transcribing", progress_percent=25)

        # Use language from config (e.g., "de" for German lectures)
        from app.config import config
        language = config.transcription.language

        transcript_result = transcription_service.transcribe(
            audio_path,
            language=language
        )

        # Format transcript for storage (with timestamps every ~60 seconds)
        formatted_transcript = transcription_service.format_transcript_with_timestamps(
            transcript_result["segments"],
            interval_seconds=60
        )

        # Save full transcript to database
        db.save_transcript(lecture_id, formatted_transcript)

        logger.info(f"[{lecture_id}] Transcription completed: {len(transcript_result['segments'])} segments")
        db.update_lecture_status(lecture_id, "transcribing", progress_percent=50)

        # ==================== STEP 3: Chunk Transcript ====================
        logger.info(f"[{lecture_id}] Step 3/6: Chunking transcript")
        db.update_lecture_status(lecture_id, "embedding", progress_percent=55)

        chunks = chunker.chunk_transcript(transcript_result["segments"])

        logger.info(f"[{lecture_id}] Created {len(chunks)} chunks")
        db.update_lecture_status(lecture_id, "embedding", progress_percent=60)

        # ==================== STEP 4: Clean Chunks with LLM ====================
        logger.info(f"[{lecture_id}] Step 4/6: Cleaning chunks with LLM")

        cleaned_chunks = llm_service.clean_transcript_chunks(
            chunks,
            text_key="text",
            show_progress=True
        )

        logger.info(f"[{lecture_id}] Cleaned {len(cleaned_chunks)} chunks")
        db.update_lecture_status(lecture_id, "embedding", progress_percent=70)

        # ==================== STEP 5: Generate Embeddings ====================
        logger.info(f"[{lecture_id}] Step 5/6: Generating embeddings")

        chunks_with_embeddings = embedding_service.embed_chunks(
            cleaned_chunks,
            text_key="text",
            show_progress=True
        )

        logger.info(f"[{lecture_id}] Generated {len(chunks_with_embeddings)} embeddings")
        db.update_lecture_status(lecture_id, "embedding", progress_percent=90)

        # ==================== STEP 6: Save to Database ====================
        logger.info(f"[{lecture_id}] Step 6/6: Saving chunks to database")

        db.save_chunks(lecture_id, chunks_with_embeddings)

        logger.info(f"[{lecture_id}] Saved {len(chunks_with_embeddings)} chunks to database")
        db.update_lecture_status(lecture_id, "completed", progress_percent=100)

        logger.info(f"[{lecture_id}] ✓ Processing completed successfully!")

    except AudioExtractionError as e:
        logger.error(f"[{lecture_id}] Audio extraction failed: {e}")
        db.update_lecture_status(lecture_id, "failed", error_message=str(e))
    except TranscriptionError as e:
        logger.error(f"[{lecture_id}] Transcription failed: {e}")
        db.update_lecture_status(lecture_id, "failed", error_message=str(e))
    except ChunkingError as e:
        logger.error(f"[{lecture_id}] Chunking failed: {e}")
        db.update_lecture_status(lecture_id, "failed", error_message=str(e))
    except EmbeddingError as e:
        logger.error(f"[{lecture_id}] Embedding generation failed: {e}")
        db.update_lecture_status(lecture_id, "failed", error_message=str(e))
    except LLMError as e:
        logger.error(f"[{lecture_id}] LLM cleanup failed: {e}")
        db.update_lecture_status(lecture_id, "failed", error_message=str(e))
    except DatabaseError as e:
        logger.error(f"[{lecture_id}] Database error: {e}")
        db.update_lecture_status(lecture_id, "failed", error_message=str(e))
    except Exception as e:
        logger.error(f"[{lecture_id}] Unexpected error: {e}", exc_info=True)
        db.update_lecture_status(lecture_id, "failed", error_message=f"Unexpected error: {str(e)}")


@router.post("", response_model=LectureResponse)
async def create_lecture(
    lecture: LectureCreate,
    background_tasks: BackgroundTasks
):
    """
    Create a new lecture and start processing pipeline in the background.

    Processing steps:
    1. Download audio from URL
    2. Transcribe with Whisper API
    3. Chunk transcript into segments
    4. Generate embeddings
    5. Store in database

    The lecture will be processed asynchronously. Use the returned lecture_id
    to check processing status via GET /api/lectures/{lecture_id}/status
    """
    try:
        # Create lecture record in database
        lecture_id = db.create_lecture(
            url=lecture.url,
            course_name=lecture.course_name,
            lecture_number=lecture.lecture_number,
            lecture_date=lecture.date
        )

        # Start background processing
        background_tasks.add_task(process_lecture_background, lecture_id, lecture.url)

        logger.info(f"Created lecture {lecture_id} for URL: {lecture.url}")

        return LectureResponse(
            lecture_id=lecture_id,
            status="processing"
        )

    except DatabaseError as e:
        logger.error(f"Failed to create lecture: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error creating lecture: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.get("/{lecture_id}/status")
async def get_lecture_status(lecture_id: str):
    """Get the processing status of a lecture."""
    try:
        lecture = db.get_lecture(lecture_id)

        if not lecture:
            raise HTTPException(status_code=404, detail="Lecture not found")

        return {
            "lecture_id": lecture_id,
            "status": lecture["status"],
            "progress_percent": lecture["progress_percent"],
            "error_message": lecture["error_message"]
        }

    except DatabaseError as e:
        logger.error(f"Database error getting lecture status: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("")
async def list_lectures():
    """List all lectures."""
    try:
        lectures = db.list_lectures()
        return {"lectures": lectures}

    except DatabaseError as e:
        logger.error(f"Database error listing lectures: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/{lecture_id}/transcript")
async def get_transcript(lecture_id: str):
    """
    Get the full transcript for a lecture with timestamps.

    Returns transcript formatted with timestamps every ~60 seconds,
    suitable for clickable navigation in the UI.
    """
    try:
        lecture = db.get_lecture(lecture_id)

        if not lecture:
            raise HTTPException(status_code=404, detail="Lecture not found")

        if lecture["status"] != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Lecture is not ready yet (status: {lecture['status']})"
            )

        if not lecture["full_transcript"]:
            raise HTTPException(
                status_code=404,
                detail="Transcript not available for this lecture"
            )

        return {
            "lecture_id": lecture_id,
            "transcript": lecture["full_transcript"]
        }

    except HTTPException:
        raise
    except DatabaseError as e:
        logger.error(f"Database error getting transcript: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error getting transcript: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
