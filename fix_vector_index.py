"""
Fix pgvector index - the IVFFlat index might not be working correctly with LIMIT.

We'll recreate it or switch to HNSW (better for small-medium datasets).
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
    print("FIX PGVECTOR INDEX")
    print("="*80)

    db = DatabaseService()
    conn = db._get_conn()

    try:
        with conn.cursor() as cur:
            # Check current index
            print("\n[1] Checking current index...")
            cur.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'lecture_chunks'
                AND indexname LIKE '%embedding%'
            """)

            result = cur.fetchone()
            if result:
                idx_name, idx_def = result
                print(f"✓ Found index: {idx_name}")
                print(f"  Definition: {idx_def}")
            else:
                print("⚠️  No embedding index found")

            # Drop existing index
            print("\n[2] Dropping existing index...")
            cur.execute("DROP INDEX IF EXISTS lecture_chunks_embedding_idx")
            conn.commit()
            print("✓ Dropped index")

            # Test without index
            print("\n[3] Testing search WITHOUT index...")
            test_vec = '[' + ','.join(['0.1'] * 1536) + ']'
            cur.execute("""
                SELECT COUNT(*)
                FROM lecture_chunks c
                ORDER BY c.embedding <=> %s::vector
                LIMIT 5
            """, [test_vec])
            count = cur.fetchone()[0]
            print(f"✓ Returns {count} results without index")

            if count == 0:
                print("\n❌ Problem persists even without index!")
                print("   This is a deeper issue - possibly with the embedding data format")
                return

            # Create new HNSW index (better than IVFFlat for most cases)
            print("\n[4] Creating new HNSW index...")
            print("  (HNSW is better than IVFFlat for small-medium datasets)")

            try:
                cur.execute("""
                    CREATE INDEX lecture_chunks_embedding_idx
                    ON lecture_chunks
                    USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64)
                """)
                conn.commit()
                print("✓ Created HNSW index")
                index_type = "HNSW"
            except Exception as e:
                if "hnsw" in str(e).lower():
                    print("⚠️  HNSW not available, falling back to IVFFlat...")

                    # Fallback to IVFFlat but with better parameters
                    cur.execute("""
                        CREATE INDEX lecture_chunks_embedding_idx
                        ON lecture_chunks
                        USING ivfflat (embedding vector_cosine_ops)
                        WITH (lists = 10)
                    """)
                    conn.commit()
                    print("✓ Created IVFFlat index (with lists=10 for small dataset)")
                    index_type = "IVFFlat"
                else:
                    raise

            # Test with new index
            print(f"\n[5] Testing search WITH new {index_type} index...")
            cur.execute("""
                SELECT COUNT(*)
                FROM lecture_chunks c
                ORDER BY c.embedding <=> %s::vector
                LIMIT 5
            """, [test_vec])
            count = cur.fetchone()[0]
            print(f"✓ Returns {count} results with new index")

            if count > 0:
                print("\n✅ SUCCESS! Index is now working.")
            else:
                print("\n⚠️  Still returns 0 results - trying without index...")

                # Drop index again
                cur.execute("DROP INDEX IF EXISTS lecture_chunks_embedding_idx")
                conn.commit()
                print("✓ Removed index - queries will use sequential scan")
                print("  (Slower but will work)")

            print("\n" + "="*80)
            print("DONE - try the RAG system now")
            print("="*80)

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db._put_conn(conn)

if __name__ == "__main__":
    main()
