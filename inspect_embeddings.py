"""
Deep inspection of embeddings in database.
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

logging.basicConfig(level=logging.INFO)

def main():
    print("\n" + "="*80)
    print("DEEP EMBEDDING INSPECTION")
    print("="*80)

    db = DatabaseService()
    conn = db._get_conn()

    try:
        with conn.cursor() as cur:
            # Get first chunk's embedding
            print("\n[1] Fetching first chunk with embedding...")
            cur.execute("""
                SELECT
                    id,
                    text,
                    embedding IS NULL as is_null,
                    embedding IS NOT NULL as has_embedding
                FROM lecture_chunks
                LIMIT 1
            """)
            result = cur.fetchone()

            if result:
                chunk_id, text, is_null, has_emb = result
                print(f"✓ Chunk ID: {chunk_id}")
                print(f"  Text: {text[:80]}...")
                print(f"  Embedding IS NULL: {is_null}")
                print(f"  Embedding IS NOT NULL: {has_emb}")

            # Try to get the actual embedding value
            print("\n[2] Trying to fetch actual embedding...")
            try:
                cur.execute("""
                    SELECT embedding
                    FROM lecture_chunks
                    WHERE embedding IS NOT NULL
                    LIMIT 1
                """)
                result = cur.fetchone()
                if result:
                    emb = result[0]
                    print(f"✓ Got embedding object: {type(emb)}")
                    print(f"  String repr: {str(emb)[:100]}...")
                else:
                    print("❌ No rows returned!")
            except Exception as e:
                print(f"❌ Failed to fetch embedding: {e}")

            # Count NULL vs NOT NULL
            print("\n[3] Counting NULL embeddings...")
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE embedding IS NULL) as null_count,
                    COUNT(*) FILTER (WHERE embedding IS NOT NULL) as not_null_count,
                    COUNT(*) as total
                FROM lecture_chunks
            """)
            result = cur.fetchone()
            null_count, not_null_count, total = result
            print(f"  NULL embeddings: {null_count}/{total}")
            print(f"  NOT NULL embeddings: {not_null_count}/{total}")

            if null_count == total:
                print("\n❌ ALL EMBEDDINGS ARE NULL!")
                print("   This is why vector search returns nothing.")
                print("   You need to re-embed the chunks.")
                return

            # Try a different query approach
            print("\n[4] Testing simplified vector query...")
            try:
                # Create a simple test vector
                test_vec = '[' + ','.join(['0.1'] * 1536) + ']'

                # Simplest possible query
                cur.execute("""
                    SELECT
                        id,
                        text,
                        embedding <=> %s::vector as distance
                    FROM lecture_chunks
                    WHERE embedding IS NOT NULL
                    LIMIT 1
                """, [test_vec])

                results = cur.fetchall()
                print(f"✓ Simple query returned {len(results)} results")

                if results:
                    for chunk_id, text, dist in results:
                        print(f"  - ID: {chunk_id}")
                        print(f"    Distance: {dist}")
                        print(f"    Text: {text[:80]}...")
                else:
                    print("❌ Even simple query returns nothing!")

            except Exception as e:
                print(f"❌ Simple query failed: {e}")
                import traceback
                traceback.print_exc()

            # Check the JOIN
            print("\n[5] Testing query WITH join...")
            try:
                test_vec = '[' + ','.join(['0.1'] * 1536) + ']'

                cur.execute("""
                    SELECT
                        c.id,
                        l.course_name,
                        c.embedding <=> %s::vector as distance
                    FROM lecture_chunks c
                    JOIN lectures l ON c.lecture_id = l.id
                    WHERE c.embedding IS NOT NULL
                    LIMIT 1
                """, [test_vec])

                results = cur.fetchall()
                print(f"✓ Query with JOIN returned {len(results)} results")

                if results:
                    for chunk_id, course, dist in results:
                        print(f"  - ID: {chunk_id}")
                        print(f"    Course: {course}")
                        print(f"    Distance: {dist}")
                else:
                    print("❌ JOIN query also returns nothing!")

            except Exception as e:
                print(f"❌ JOIN query failed: {e}")
                import traceback
                traceback.print_exc()

            # Check lecture_id references
            print("\n[6] Checking lecture_id references...")
            cur.execute("""
                SELECT
                    c.lecture_id,
                    l.id IS NOT NULL as lecture_exists,
                    COUNT(*) as chunk_count
                FROM lecture_chunks c
                LEFT JOIN lectures l ON c.lecture_id = l.id
                GROUP BY c.lecture_id, l.id
            """)
            for lecture_id, exists, count in cur.fetchall():
                status = "✓" if exists else "❌"
                print(f"  {status} Lecture {lecture_id}: {count} chunks, exists={exists}")

    finally:
        db._put_conn(conn)

    print("\n" + "="*80)
    print("INSPECTION COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()
