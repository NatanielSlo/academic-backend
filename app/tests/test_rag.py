"""
Test script for RAG Q&A system.

Tests the complete RAG pipeline:
1. Retrieves lecture from database
2. Asks questions about lecture content
3. Shows retrieved context chunks
4. Displays LLM answer with sources

Usage:
    python test_rag.py
"""

import sys
import logging
from pathlib import Path
import os

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.rag import RAGService, RAGError
from app.services.database import DatabaseService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_rag_qa():
    """Test RAG Q&A with sample questions."""

    print("\n" + "="*70)
    print("RAG Q&A TEST")
    print("="*70)

    # Initialize services
    rag = RAGService()
    db = DatabaseService()

    # Get a lecture from database to test with
    print("\nFetching lectures from database...")
    lectures = db.list_lectures()

    if not lectures:
        print("❌ No lectures found in database!")
        print("   Please run the full pipeline first to process a lecture.")
        return

    # Find a completed lecture
    completed_lectures = [l for l in lectures if l['status'] == 'completed']

    if not completed_lectures:
        print("❌ No completed lectures found!")
        print("   Please wait for a lecture to finish processing.")
        return

    lecture = completed_lectures[0]
    print(f"✓ Using lecture: {lecture['course_name']} #{lecture['lecture_number']}")
    print(f"  ID: {lecture['id']}")
    print()

    # Sample questions (German for TUM lectures)
    questions = [
        "Was ist dynamic programming?",
        "Wie funktioniert das Praktikum?",
        "Wann findet die Vorlesung statt?",
        "Was ist der Unterschied zwischen EIDI und PGDP?",
    ]

    # Test each question
    for i, question in enumerate(questions, 1):
        print("\n" + "="*70)
        print(f"QUESTION {i}/{len(questions)}")
        print("="*70)
        print(f"❓ {question}\n")

        try:
            # Test with global scope
            result = rag.answer_question(question, scope="global")

            # Display answer
            print("💬 ANSWER:")
            print("-" * 70)
            print(result['answer'])
            print()

            # Display sources
            sources = result['sources']
            print(f"📚 SOURCES ({len(sources)}):")
            print("-" * 70)

            if not sources:
                print("   (No sources found)")
            else:
                for j, source in enumerate(sources, 1):
                    course = source['course_name'] or 'Unknown'
                    lecture_num = source['lecture_number'] or '?'
                    timestamp = source['timestamp']
                    similarity = source['similarity']

                    print(f"   [{j}] {course} Vorlesung {lecture_num} @ {timestamp}")
                    print(f"       Similarity: {similarity:.3f}")
                    print(f"       {source['chunk_text']}")
                    print()

        except RAGError as e:
            print(f"❌ RAG Error: {e}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()

    # Test scope-specific queries
    print("\n" + "="*70)
    print("TESTING LECTURE-SPECIFIC SCOPE")
    print("="*70)

    question = "Was wurde in dieser Vorlesung besprochen?"
    print(f"❓ {question}")
    print(f"   (Scope: lecture, ID: {lecture['id']})\n")

    try:
        result = rag.answer_question(
            question=question,
            scope="lecture",
            scope_id=str(lecture['id'])
        )

        print("💬 ANSWER:")
        print("-" * 70)
        print(result['answer'])
        print()

        print(f"📚 SOURCES: {len(result['sources'])} chunks from this specific lecture")

    except RAGError as e:
        print(f"❌ RAG Error: {e}")

    # Summary
    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)
    print("✓ RAG Q&A system is working!")
    print()
    print("Next steps:")
    print("  - Test via API: POST http://localhost:8000/api/chat")
    print("  - Check API docs: http://localhost:8000/docs")
    print("  - Try different scopes: global, course, lecture")
    print()


if __name__ == "__main__":
    test_rag_qa()
