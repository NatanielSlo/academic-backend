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

import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _blocks_to_segments(blocks: list) -> list:
    """
    Turn cleaned ~60s transcript blocks ({timestamp_seconds, text}) into finer,
    sentence-level pseudo-segments ({start, end, text}) for the chunker.

    Splitting at sentence boundaries gives the chunker enough granularity to build
    proper overlapping chunks for embeddings, while timestamps stay at the block's
    resolution (good enough for RAG citations).
    """
    segments = []
    for i, block in enumerate(blocks):
        text = (block.get("text") or "").strip()
        if not text:
            continue
        start = block.get("timestamp_seconds", 0)
        # End of this block ≈ start of the next block (last block: +60s).
        if i + 1 < len(blocks):
            end = blocks[i + 1].get("timestamp_seconds", start)
        else:
            end = start + 60
        for sentence in _SENTENCE_SPLIT.split(text):
            sentence = sentence.strip()
            if sentence:
                segments.append({"start": start, "end": end, "text": sentence})
    return segments


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
        db.update_lecture_status(
            lecture_id, "downloading", progress_percent=10,
            progress_message="Rozpoczynanie pobierania…"
        )

        def on_download(pct: float, phase: str):
            # Map download 0-100% into overall 10-24%; conversion sits at 24%.
            if phase == "converting":
                db.update_lecture_status(
                    lecture_id, "downloading", progress_percent=24,
                    progress_message="Konwersja do MP3…"
                )
            else:
                overall = 10 + int(pct * 0.14)
                db.update_lecture_status(
                    lecture_id, "downloading", progress_percent=overall,
                    progress_message=f"Pobieranie audio: {int(pct)}%"
                )

        audio_path = audio_extractor.extract_audio(url, lecture_id, progress_callback=on_download)
        db.update_lecture_audio_path(lecture_id, str(audio_path))

        logger.info(f"[{lecture_id}] Audio downloaded: {audio_path}")
        db.update_lecture_status(
            lecture_id, "downloading", progress_percent=25,
            progress_message="Audio pobrane"
        )

        # ==================== STEP 2: Transcribe Audio ====================
        logger.info(f"[{lecture_id}] Step 2/6: Transcribing audio")
        db.update_lecture_status(
            lecture_id, "transcribing", progress_percent=25,
            progress_message="Transkrypcja audio…"
        )

        # Use language from config (e.g., "de" for German lectures)
        from app.config import config
        language = config.transcription.language

        def on_transcribe_chunk(done: int, total: int):
            # Whisper processes the audio in ~10-min chunks; map to overall 25-48%.
            overall = 25 + int((done / total) * 23)
            db.update_lecture_status(
                lecture_id, "transcribing", progress_percent=overall,
                progress_message=f"Transkrypcja: część {done}/{total}"
            )

        transcript_result = transcription_service.transcribe(
            audio_path,
            language=language,
            chunk_callback=on_transcribe_chunk
        )

        # Format transcript for storage (with timestamps every ~60 seconds)
        formatted_transcript = transcription_service.format_transcript_with_timestamps(
            transcript_result["segments"],
            interval_seconds=60
        )

        # Save full transcript to database
        db.save_transcript(lecture_id, formatted_transcript)

        logger.info(f"[{lecture_id}] Transcription completed: {len(transcript_result['segments'])} segments")
        db.update_lecture_status(
            lecture_id, "transcribing", progress_percent=50,
            progress_message="Transkrypcja zakończona"
        )

        # ==================== STEP 3: Clean Transcript with LLM ====================
        # Clean ONCE over the ~60s timestamped blocks (non-overlapping), then reuse the
        # result for both content generation/display and embeddings. Cleaning here (not
        # on overlapping chunks) avoids re-processing overlap regions and yields a clean
        # full transcript we can persist.
        logger.info(f"[{lecture_id}] Step 3/6: Cleaning transcript with LLM")
        db.update_lecture_status(
            lecture_id, "embedding", progress_percent=55,
            progress_message="Czyszczenie transkryptu…"
        )

        # Throttle DB writes to ~20 updates regardless of block count.
        clean_total = max(1, len(formatted_transcript))
        clean_step = max(1, clean_total // 20)

        def on_clean(done: int, total: int):
            if done != total and done % clean_step != 0:
                return
            overall = 55 + int((done / total) * 10)  # 55..65
            db.update_lecture_status(
                lecture_id, "embedding", progress_percent=overall,
                progress_message=f"Czyszczenie transkryptu: {done}/{total} bloków"
            )

        cleaned_transcript = llm_service.clean_transcript_chunks(
            formatted_transcript,
            text_key="text",
            show_progress=True,
            progress_callback=on_clean
        )
        db.save_cleaned_transcript(lecture_id, cleaned_transcript)

        logger.info(f"[{lecture_id}] Cleaned transcript ({len(cleaned_transcript)} blocks)")
        db.update_lecture_status(
            lecture_id, "embedding", progress_percent=65,
            progress_message="Transkrypt wyczyszczony"
        )

        # ==================== STEP 4: Chunk Cleaned Transcript ====================
        logger.info(f"[{lecture_id}] Step 4/6: Chunking cleaned transcript")

        pseudo_segments = _blocks_to_segments(cleaned_transcript)
        chunks = chunker.chunk_transcript(pseudo_segments)

        logger.info(f"[{lecture_id}] Created {len(chunks)} chunks from cleaned transcript")
        db.update_lecture_status(
            lecture_id, "embedding", progress_percent=70,
            progress_message=f"Podzielono na {len(chunks)} fragmentów"
        )

        # ==================== STEP 5: Generate Embeddings ====================
        logger.info(f"[{lecture_id}] Step 5/6: Generating embeddings")

        def on_embed(batch: int, total: int):
            overall = 70 + int((batch / total) * 20)  # 70..90
            db.update_lecture_status(
                lecture_id, "embedding", progress_percent=overall,
                progress_message=f"Generowanie embeddingów: batch {batch}/{total}"
            )

        chunks_with_embeddings = embedding_service.embed_chunks(
            chunks,
            text_key="text",
            show_progress=True,
            progress_callback=on_embed
        )

        logger.info(f"[{lecture_id}] Generated {len(chunks_with_embeddings)} embeddings")
        db.update_lecture_status(
            lecture_id, "embedding", progress_percent=90,
            progress_message="Embeddingi wygenerowane"
        )

        # ==================== STEP 6: Save to Database ====================
        logger.info(f"[{lecture_id}] Step 6/6: Saving chunks to database")
        db.update_lecture_status(
            lecture_id, "embedding", progress_percent=95,
            progress_message="Zapisywanie do bazy…"
        )

        db.save_chunks(lecture_id, chunks_with_embeddings)

        logger.info(f"[{lecture_id}] Saved {len(chunks_with_embeddings)} chunks to database")
        db.update_lecture_status(
            lecture_id, "completed", progress_percent=100,
            progress_message="Gotowe"
        )

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

    Any of course_name, lecture_number, date that are omitted will be
    auto-extracted from the URL before the record is created.

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
        # Auto-extract metadata for any fields the caller left blank
        course_name = lecture.course_name
        lecture_number = lecture.lecture_number
        lecture_date = lecture.date

        if not course_name or not lecture_date:
            meta = audio_extractor.extract_metadata(lecture.url)
            if not course_name:
                course_name = meta.get('course_name')
            if not lecture_number:
                lecture_number = meta.get('lecture_number')
            if not lecture_date:
                lecture_date = meta.get('date')
            logger.info(f"Auto-extracted metadata for {lecture.url}: {meta}")

        # Create lecture record in database
        lecture_id = db.create_lecture(
            url=lecture.url,
            course_name=course_name,
            lecture_number=lecture_number,
            lecture_date=lecture_date,
        )

        # Start background processing
        background_tasks.add_task(process_lecture_background, lecture_id, lecture.url)

        logger.info(f"Created lecture {lecture_id} for URL: {lecture.url}")

        return LectureResponse(
            lecture_id=lecture_id,
            status="processing",
            course_name=course_name,
            lecture_number=lecture_number,
            date=lecture_date,
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
            "progress_message": lecture.get("progress_message"),
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
            "transcript": lecture["full_transcript"],
            "cleaned_transcript": lecture.get("cleaned_transcript"),
        }

    except HTTPException:
        raise
    except DatabaseError as e:
        logger.error(f"Database error getting transcript: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error getting transcript: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
