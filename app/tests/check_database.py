"""
Check database state - how many lectures and chunks we have.
"""

import sys
import logging
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.database import DatabaseService
from app.services.embeddings import EmbeddingService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

def main():
    print("\n" + "="*80)
    print("DATABASE STATE CHECK")
    print("="*80)

    db = DatabaseService()

    # Check connection
    print("\n[1] Testing database connection...")
    if db.test_connection():
        print("✓ Database connection OK")
    else:
        print("❌ Database connection FAILED")
        return

    # Check lectures
    print("\n[2] Checking lectures...")
    conn = db._get_conn()
    try:
        with conn.cursor() as cur:
            # Count total lectures
            cur.execute("SELECT COUNT(*) FROM lectures")
            total_lectures = cur.fetchone()[0]
            print(f"✓ Total lectures: {total_lectures}")

            # Count by status
            cur.execute("""
                SELECT status, COUNT(*)
                FROM lectures
                GROUP BY status
            """)
            for status, count in cur.fetchall():
                print(f"  - {status}: {count}")

            if total_lectures == 0:
                print("\n⚠️  No lectures in database!")
                print("   Run the pipeline to process a lecture first.")
                return

            # Show sample lectures
            cur.execute("""
                SELECT id, course_name, lecture_number, status, created_at
                FROM lectures
                ORDER BY created_at DESC
                LIMIT 5
            """)
            print("\n  Recent lectures:")
            for row in cur.fetchall():
                lecture_id, course, num, status, created = row
                print(f"    - {course} #{num} ({status}) - ID: {lecture_id}")

    finally:
        db._put_conn(conn)

    # Check chunks
    print("\n[3] Checking lecture chunks...")
    conn = db._get_conn()
    try:
        with conn.cursor() as cur:
            # Count total chunks
            cur.execute("SELECT COUNT(*) FROM lecture_chunks")
            total_chunks = cur.fetchone()[0]
            print(f"✓ Total chunks: {total_chunks}")

            if total_chunks == 0:
                print("\n❌ NO CHUNKS IN DATABASE!")
                print("   This is why search returns 0 results.")
                print("   The pipeline may have failed during chunk generation.")
                return

            # Check chunks per lecture
            cur.execute("""
                SELECT
                    l.course_name,
                    l.lecture_number,
                    COUNT(c.id) as chunk_count
                FROM lectures l
                LEFT JOIN lecture_chunks c ON l.id = c.lecture_id
                GROUP BY l.id, l.course_name, l.lecture_number
                ORDER BY chunk_count DESC
            """)
            print("\n  Chunks per lecture:")
            for course, num, count in cur.fetchall():
                print(f"    - {course} #{num}: {count} chunks")

            # Check if embeddings exist
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(embedding) as with_embedding
                FROM lecture_chunks
            """)
            total, with_emb = cur.fetchone()
            print(f"\n  Embeddings: {with_emb}/{total} chunks have embeddings")

            if with_emb == 0:
                print("\n❌ NO EMBEDDINGS IN CHUNKS!")
                print("   This is why vector search returns nothing.")
                return

            # Check embedding dimensions (pgvector specific)
            try:
                cur.execute("""
                    SELECT vector_dims(embedding) as dims
                    FROM lecture_chunks
                    WHERE embedding IS NOT NULL
                    LIMIT 1
                """)
                result = cur.fetchone()
                if result:
                    dims = result[0]
                    print(f"  Embedding dimensions: {dims}")
            except Exception as e:
                print(f"  Could not check dimensions: {e}")

            # Show sample chunk
            try:
                cur.execute("""
                    SELECT
                        c.text,
                        c.start_timestamp_seconds,
                        l.course_name,
                        vector_dims(c.embedding) as emb_dims
                    FROM lecture_chunks c
                    JOIN lectures l ON c.lecture_id = l.id
                    WHERE c.embedding IS NOT NULL
                    LIMIT 1
                """)
                result = cur.fetchone()
                if result:
                    text, timestamp, course, dims = result
                    print(f"\n  Sample chunk:")
                    print(f"    Course: {course}")
                    print(f"    Timestamp: {timestamp}s")
                    print(f"    Text: {text[:100]}...")
                    print(f"    Embedding: {dims} dimensions")
            except Exception as e:
                print(f"\n  Could not fetch sample chunk: {e}")

    finally:
        db._put_conn(conn)

    # Test vector search manually
    print("\n[4] Testing vector search...")
    print("  Generating test embedding...")

    emb_service = EmbeddingService()
    test_question = "Was ist dynamic programming?"
    test_embedding = emb_service.embed_text(test_question)

    print(f"  ✓ Test embedding: {len(test_embedding)} dimensions")
    print(f"  Running similarity search...")

    conn = db._get_conn()
    try:
        with conn.cursor() as cur:
            # Manual vector search
            embedding_str = '[' + ','.join(map(str, test_embedding)) + ']'

            query = """
                SELECT
                    c.id,
                    c.text,
                    l.course_name,
                    l.lecture_number,
                    1 - (c.embedding <=> %s::vector) as similarity
                FROM lecture_chunks c
                JOIN lectures l ON c.lecture_id = l.id
                WHERE c.embedding IS NOT NULL
                ORDER BY c.embedding <=> %s::vector
                LIMIT 5
            """

            print(f"\n  SQL Query:")
            print(f"    {query}")
            print(f"    Params: [embedding_vector (1536 dims)]")

            cur.execute(query, [embedding_str, embedding_str])
            results = cur.fetchall()

            print(f"\n  ✓ Query returned {len(results)} results")

            if len(results) == 0:
                print("\n❌ VECTOR SEARCH RETURNED NOTHING!")
                print("   Possible issues:")
                print("   1. pgvector extension not installed")
                print("   2. Embedding column not properly configured")
                print("   3. Embeddings are NULL or corrupted")
            else:
                print("\n  Results:")
                for row in results:
                    chunk_id, text, course, lecture, sim = row
                    print(f"    - Similarity: {sim:.4f} | {course} L{lecture}")
                    print(f"      {text[:80]}...")

    except Exception as e:
        print(f"\n❌ Vector search failed with error:")
        print(f"   {e}")
        import traceback
        traceback.print_exc()
    finally:
        db._put_conn(conn)

    print("\n" + "="*80)
    print("DIAGNOSTICS COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()
