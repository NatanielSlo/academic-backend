"""
Test script to process existing transcript through the pipeline.

Usage:
    python test_pipeline_from_transcript.py [transcript_file.json]
    python test_pipeline_from_transcript.py --resume [checkpoint_file.json]

If no file provided, uses sample data.
"""

import sys
import json
import logging
from pathlib import Path
from datetime import date
import argparse

from app.services.chunker import TextChunker
from app.services.llm import LLMService
from app.services.embeddings import EmbeddingService
from app.services.database import DatabaseService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_transcript_from_file(file_path: str):
    """Load transcript from JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Support multiple formats
    # Format 1: {"segments": [...]}
    if "segments" in data:
        return data["segments"]

    # Format 2: {"raw_result": {"segments": [...]}}
    if "raw_result" in data and "segments" in data["raw_result"]:
        return data["raw_result"]["segments"]

    raise ValueError("Transcript file must contain 'segments' key or 'raw_result.segments' key")


def get_sample_transcript():
    """Generate sample transcript for testing."""
    return [
        {
            "start": 0.0,
            "end": 5.5,
            "text": "Um, so hello everyone, uh, welcome to, like, the first lecture of EIDI."
        },
        {
            "start": 5.5,
            "end": 12.0,
            "text": "So today we're gonna talk about, um, dynamic programming, okay?"
        },
        {
            "start": 12.0,
            "end": 18.5,
            "text": "Dynamic programming is, uh, you know, it's a method for solving, like, complex problems."
        },
        {
            "start": 18.5,
            "end": 25.0,
            "text": "So it breaks them down into, um, simpler subproblems that are, uh, easier to solve."
        },
        {
            "start": 25.0,
            "end": 32.0,
            "text": "Um, let's start with the, uh, the Fibonacci sequence as, like, our first example."
        },
        {
            "start": 32.0,
            "end": 40.0,
            "text": "So the Fibonacci sequence is, um, defined recursively where, uh, F of n equals F of n minus 1 plus F of n minus 2."
        },
        {
            "start": 40.0,
            "end": 47.0,
            "text": "And, um, you know, the base cases are, like, F of 0 equals 0 and F of 1 equals 1."
        },
        {
            "start": 47.0,
            "end": 55.0,
            "text": "So if we, uh, implement this naively using, like, recursion, um, we'll see that it's very slow."
        },
        {
            "start": 55.0,
            "end": 62.0,
            "text": "The time complexity is, uh, exponential - it's O of 2 to the n, which is, you know, really bad."
        },
        {
            "start": 62.0,
            "end": 70.0,
            "text": "But, um, with dynamic programming we can, like, optimize this to O of n time complexity."
        }
    ]


def test_pipeline(segments=None, use_database=False, lecture_id=None, resume_from=None):
    """
    Test the pipeline from transcript to embeddings.

    Args:
        segments: List of transcript segments (required if not resuming)
        use_database: Whether to actually save to database
        lecture_id: Optional lecture ID (required if use_database=True)
        resume_from: Path to checkpoint file to resume from
    """
    print("\n" + "="*70)
    print("TESTING PIPELINE FROM TRANSCRIPT")
    if resume_from:
        print("RESUMING FROM CHECKPOINT")
    print("="*70)

    cleaned_chunks = None

    if resume_from:
        # ==================== RESUME: Load checkpoint ====================
        print("\n[RESUME] LOADING CHECKPOINT")
        print("-" * 70)

        checkpoint_path = Path(resume_from)
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

        cleaned_chunks = LLMService.load_checkpoint(checkpoint_path)
        print(f"✓ Loaded {len(cleaned_chunks)} cleaned chunks from checkpoint")
        print(f"  File: {checkpoint_path}")
        print()

    else:
        # ==================== STEP 1: Chunking ====================
        print("\n[STEP 1] CHUNKING")
        print("-" * 70)

        chunker = TextChunker()
        chunks = chunker.chunk_transcript(segments)

        print(f"\n✓ Created {len(chunks)} chunks\n")
        for i, chunk in enumerate(chunks[:3]):  # Show first 3
            print(f"Chunk {i}:")
            print(f"  Time: {chunk['start_timestamp_seconds']}s - {chunk['end_timestamp_seconds']}s")
            print(f"  Tokens: {chunk['token_count']}")
            print(f"  Text: {chunk['text'][:100]}...")
            print()

        if len(chunks) > 3:
            print(f"... and {len(chunks) - 3} more chunks\n")

        # ==================== STEP 2: LLM Cleanup ====================
        print("\n[STEP 2] LLM CLEANUP")
        print("-" * 70)

        llm_service = LLMService()
        cleaned_chunks = llm_service.clean_transcript_chunks(chunks, show_progress=True)

        print("\n✓ Chunks cleaned!\n")
        print("BEFORE vs AFTER comparison:\n")
        for i in range(min(2, len(chunks))):
            print(f"Chunk {i}:")
            print(f"  BEFORE: {chunks[i]['text'][:150]}...")
            print(f"  AFTER:  {cleaned_chunks[i]['text'][:150]}...")
            print()

    # ==================== STEP 3: Generate Embeddings ====================
    print("\n[STEP 3] GENERATE EMBEDDINGS")
    print("-" * 70)
    print(f"Processing {len(cleaned_chunks)} chunks...")

    embedding_service = EmbeddingService()
    chunks_with_embeddings = embedding_service.embed_chunks(
        cleaned_chunks,
        text_key="text",
        show_progress=True
    )

    print(f"\n✓ Generated {len(chunks_with_embeddings)} embeddings")
    print(f"  Embedding dimension: {len(chunks_with_embeddings[0]['embedding'])}")

    # ==================== STEP 4: Save to Database (Optional) ====================
    if use_database:
        if not lecture_id:
            raise ValueError("lecture_id required when use_database=True")

        print("\n[STEP 4] SAVE TO DATABASE")
        print("-" * 70)

        db = DatabaseService()

        # Test connection
        if not db.test_connection():
            print("✗ Database connection failed - skipping save")
            return chunks_with_embeddings

        # Save chunks
        db.save_chunks(lecture_id, chunks_with_embeddings)
        print(f"\n✓ Saved {len(chunks_with_embeddings)} chunks to database")
        print(f"  Lecture ID: {lecture_id}")

    else:
        print("\n[STEP 4] SAVE TO DATABASE - SKIPPED")
        print("-" * 70)
        print("Set use_database=True to save to database")

    # ==================== Summary ====================
    print("\n" + "="*70)
    print("PIPELINE TEST COMPLETE ✓")
    print("="*70)
    print(f"Processed {len(segments)} transcript segments")
    print(f"Created {len(chunks)} chunks")
    print(f"Generated {len(chunks_with_embeddings)} embeddings")
    if use_database:
        print(f"Saved to database: YES (lecture_id={lecture_id})")
    else:
        print(f"Saved to database: NO")
    print("="*70 + "\n")

    return chunks_with_embeddings


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Test pipeline from transcript")
    parser.add_argument('transcript_file', nargs='?', help='Path to transcript JSON file')
    parser.add_argument('--resume', help='Resume from checkpoint file (skip LLM cleanup)')
    args = parser.parse_args()

    segments = None
    resume_from = args.resume

    if resume_from:
        print(f"Resuming from checkpoint: {resume_from}")
    elif args.transcript_file:
        transcript_file = args.transcript_file
        print(f"Loading transcript from: {transcript_file}")
        segments = load_transcript_from_file(transcript_file)
    else:
        print("No transcript file provided - using sample data")
        segments = get_sample_transcript()

    # Ask if user wants to save to database
    print("\nDo you want to save results to database? (y/n)")
    save_to_db = input("> ").lower().strip() == 'y'

    lecture_id = None
    if save_to_db:
        # Create lecture record first
        print("\nCreating lecture record in database...")
        from app.services.database import DatabaseService

        db = DatabaseService()
        lecture_id = db.create_lecture(
            url="https://example.com/test",
            course_name="EIDI",
            lecture_number="TEST",
            lecture_date=date.today()
        )
        print(f"Created lecture: {lecture_id}")

        # Update to transcribing status
        db.update_lecture_status(lecture_id, "transcribing", progress_percent=50)

    # Run pipeline test
    try:
        result = test_pipeline(
            segments=segments,
            use_database=save_to_db,
            lecture_id=lecture_id,
            resume_from=resume_from
        )

        if save_to_db and lecture_id:
            # Mark as completed
            db = DatabaseService()
            db.update_lecture_status(lecture_id, "completed", progress_percent=100)
            print(f"\n✓ Lecture {lecture_id} marked as completed")

    except Exception as e:
        logger.error(f"Pipeline test failed: {e}", exc_info=True)
        if save_to_db and lecture_id:
            db = DatabaseService()
            db.update_lecture_status(lecture_id, "failed", error_message=str(e))
        raise


if __name__ == "__main__":
    main()
