"""
Diagnostic script for RAG system.

Shows exactly what the LLM receives and why it might say "no information".

Usage:
    python diagnose_rag.py
"""

import sys
import logging
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.rag import RAGService
from app.services.database import DatabaseService

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def diagnose_question(rag: RAGService, question: str, scope: str = "global", scope_id=None):
    """
    Diagnose a single question through the RAG pipeline.
    Shows step-by-step what happens.
    """
    print("\n" + "="*80)
    print(f"DIAGNOSING QUESTION: {question}")
    print("="*80)

    # Step 1: Embed question
    print("\n[STEP 1] Embedding question...")
    query_embedding = rag.embedding_service.embed_text(question)
    print(f"✓ Created embedding vector ({len(query_embedding)} dimensions)")

    # Step 2: Retrieve chunks BEFORE filtering
    print("\n[STEP 2] Retrieving similar chunks from database...")
    print(f"  - Scope: {scope}")
    if scope_id:
        print(f"  - Scope ID: {scope_id}")
    print(f"  - Requesting TOP {rag.top_k} chunks")
    print(f"  - Similarity threshold: {rag.similarity_threshold}")

    # Get chunks directly from DB (before filtering)
    lecture_id = scope_id if scope == "lecture" else None
    course_name = scope_id if scope == "course" else None

    all_chunks = rag.db.search_similar_chunks(
        query_embedding=query_embedding,
        top_k=rag.top_k * 2,  # Get more to see what's being filtered out
        lecture_id=lecture_id,
        course_name=course_name
    )

    print(f"\n✓ Retrieved {len(all_chunks)} chunks from database")

    # Show all chunks with similarity scores
    print("\n" + "-"*80)
    print("RETRIEVED CHUNKS (before threshold filtering):")
    print("-"*80)

    for i, chunk in enumerate(all_chunks, 1):
        similarity = chunk.get('similarity', 0)
        passed = "✓ PASS" if similarity >= rag.similarity_threshold else "✗ FILTERED OUT"

        print(f"\n[Chunk {i}] Similarity: {similarity:.4f} {passed}")
        print(f"  Course: {chunk.get('course_name', 'Unknown')}")
        print(f"  Lecture: {chunk.get('lecture_number', 'Unknown')}")
        print(f"  Timestamp: {chunk.get('start_timestamp_seconds', 0)}s")
        print(f"  Text preview: {chunk.get('text', '')[:150]}...")

        if i >= 10:  # Limit output
            remaining = len(all_chunks) - i
            if remaining > 0:
                print(f"\n  ... and {remaining} more chunks")
            break

    # Step 3: Apply threshold filter
    print("\n" + "-"*80)
    print(f"[STEP 3] Applying similarity threshold: {rag.similarity_threshold}")
    print("-"*80)

    filtered_chunks = [c for c in all_chunks if c.get('similarity', 0) >= rag.similarity_threshold]

    print(f"✓ {len(filtered_chunks)} chunks passed the threshold")
    print(f"✗ {len(all_chunks) - len(filtered_chunks)} chunks filtered out")

    if len(filtered_chunks) == 0:
        print("\n⚠️  WARNING: NO CHUNKS PASSED THE THRESHOLD!")
        print("   This is why LLM says 'no information'")
        print(f"   Consider lowering threshold or checking embedding quality")
        return

    # Step 4: Show what LLM receives
    print("\n" + "-"*80)
    print("[STEP 4] Building context for LLM")
    print("-"*80)

    context_parts = []
    for i, chunk in enumerate(filtered_chunks[:5], 1):  # Top 5 after filtering
        course = chunk.get('course_name', 'Unknown')
        lecture = chunk.get('lecture_number', 'Unknown')
        timestamp_sec = chunk.get('start_timestamp_seconds', 0)
        hours = timestamp_sec // 3600
        minutes = (timestamp_sec % 3600) // 60
        secs = timestamp_sec % 60
        timestamp = f"{hours:02d}:{minutes:02d}:{secs:02d}"
        text = chunk.get('text', '')

        context_part = f"[Quelle {i}] Kurs: {course}, Vorlesung: {lecture}, Zeit: {timestamp}\n{text}"
        context_parts.append(context_part)

    context = "\n\n".join(context_parts)

    print(f"\n✓ Context has {len(filtered_chunks[:5])} sources")
    print(f"✓ Total context length: {len(context)} characters")

    # Show the actual context LLM will see
    print("\n" + "="*80)
    print("CONTEXT THAT LLM RECEIVES:")
    print("="*80)
    print(context)
    print("="*80)

    # Step 5: Generate answer
    print("\n[STEP 5] Generating answer with LLM...")

    try:
        result = rag.answer_question(question, scope=scope, scope_id=scope_id)

        print("\n" + "="*80)
        print("FINAL ANSWER:")
        print("="*80)
        print(result['answer'])
        print("="*80)

        # Analysis
        print("\n[ANALYSIS]")
        is_no_info = any(phrase in result['answer'].lower() for phrase in [
            'keine', 'nicht finden', 'keine informationen', 'nicht vorhanden'
        ])

        if is_no_info:
            print("⚠️  LLM said 'no information' despite having context!")
            print("   Possible reasons:")
            print("   1. Context chunks are not relevant enough")
            print("   2. Prompt is too restrictive")
            print("   3. Question requires information not in the chunks")
        else:
            print("✓ LLM provided an answer based on the context")

    except Exception as e:
        print(f"\n❌ Error generating answer: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Run diagnostics on sample questions."""

    print("\n" + "="*80)
    print("RAG SYSTEM DIAGNOSTICS")
    print("="*80)

    # Initialize services
    print("\n[INIT] Initializing RAG service...")
    rag = RAGService()
    db = DatabaseService()

    print(f"✓ RAG config:")
    print(f"  - Top K: {rag.top_k}")
    print(f"  - Similarity threshold: {rag.similarity_threshold}")
    print(f"  - Embedding model: {rag.embedding_service.model}")
    print(f"  - LLM model: {rag.llm_service.simple_model}")

    # Check if we have data
    print("\n[CHECK] Checking database...")
    lectures = db.list_lectures()
    completed = [l for l in lectures if l['status'] == 'completed']

    print(f"✓ Total lectures: {len(lectures)}")
    print(f"✓ Completed lectures: {len(completed)}")

    if not completed:
        print("\n❌ No completed lectures found!")
        print("   Please process a lecture first.")
        return

    # Test questions
    test_questions = [
        "Was ist dynamic programming?",
        "Wie funktioniert Rekursion?",
        "Was wurde über Fibonacci gesagt?",
    ]

    print(f"\n{'='*80}")
    print(f"Running {len(test_questions)} diagnostic tests...")
    print(f"{'='*80}")

    for i, question in enumerate(test_questions, 1):
        print(f"\n\n{'#'*80}")
        print(f"# TEST {i}/{len(test_questions)}")
        print(f"{'#'*80}")

        diagnose_question(rag, question)

        if i < len(test_questions):
            input("\nPress ENTER to continue to next test...")

    # Summary
    print("\n\n" + "="*80)
    print("DIAGNOSTIC SUMMARY")
    print("="*80)
    print("\nKey things to check:")
    print("1. Are similarity scores high enough? (>0.5 is good)")
    print("2. Are chunks actually relevant to the questions?")
    print("3. Does LLM receive good context but still says 'no info'?")
    print("4. How many chunks are filtered out by threshold?")
    print("\nNext steps:")
    print("- If scores are low: improve embeddings or check data quality")
    print("- If chunks irrelevant: improve chunking strategy")
    print("- If LLM refuses: adjust prompt to be less restrictive")
    print("- If too many filtered: lower similarity_threshold")
    print()


if __name__ == "__main__":
    main()
