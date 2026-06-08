"""
Check pgvector extension configuration.
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
    print("PGVECTOR EXTENSION CHECK")
    print("="*80)

    db = DatabaseService()
    conn = db._get_conn()

    try:
        with conn.cursor() as cur:
            # Check if pgvector is installed
            print("\n[1] Checking pgvector extension...")
            cur.execute("""
                SELECT * FROM pg_extension WHERE extname = 'vector'
            """)
            result = cur.fetchone()

            if result:
                print("✓ pgvector extension is installed")
                print(f"  Details: {result}")
            else:
                print("❌ pgvector extension is NOT installed!")
                print("\nTo fix this, run in your database:")
                print("  CREATE EXTENSION vector;")
                return

            # Check column type
            print("\n[2] Checking lecture_chunks.embedding column type...")
            cur.execute("""
                SELECT
                    column_name,
                    data_type,
                    udt_name
                FROM information_schema.columns
                WHERE table_name = 'lecture_chunks'
                AND column_name = 'embedding'
            """)
            result = cur.fetchone()

            if result:
                col_name, data_type, udt_name = result
                print(f"✓ Column exists: {col_name}")
                print(f"  Data type: {data_type}")
                print(f"  UDT name: {udt_name}")

                if udt_name != 'vector':
                    print(f"\n⚠️  WARNING: Column type is '{udt_name}', expected 'vector'")
                    print("  This might cause issues with vector operations")
            else:
                print("❌ embedding column not found!")

            # Check actual data type in table
            print("\n[3] Checking actual embedding data...")
            cur.execute("""
                SELECT
                    pg_typeof(embedding) as type,
                    embedding IS NULL as is_null
                FROM lecture_chunks
                LIMIT 1
            """)
            result = cur.fetchone()

            if result:
                type_name, is_null = result
                print(f"✓ First row type: {type_name}")
                print(f"  Is NULL: {is_null}")
            else:
                print("❌ No rows in lecture_chunks")

            # Try simple vector operation
            print("\n[4] Testing vector operations...")

            # Test creating a vector
            try:
                cur.execute("SELECT '[1,2,3]'::vector as test_vec")
                print("✓ Can cast string to vector")
            except Exception as e:
                print(f"❌ Cannot cast to vector: {e}")
                return

            # Test distance operator
            try:
                cur.execute("SELECT '[1,2,3]'::vector <=> '[1,2,3]'::vector as dist")
                result = cur.fetchone()
                print(f"✓ Distance operator <=> works, result: {result[0]}")
            except Exception as e:
                print(f"❌ Distance operator <=> failed: {e}")
                return

            # Test with actual data
            print("\n[5] Testing with actual chunk data...")
            try:
                cur.execute("""
                    SELECT
                        id,
                        embedding <=> '[0,0,0]'::vector as dist
                    FROM lecture_chunks
                    LIMIT 1
                """)
                result = cur.fetchone()
                if result:
                    chunk_id, dist = result
                    print(f"✓ Can compute distance for chunk {chunk_id}: {dist}")
                else:
                    print("⚠️  Query returned no results")
            except Exception as e:
                print(f"❌ Distance computation failed: {e}")
                print(f"   Error type: {type(e).__name__}")
                import traceback
                traceback.print_exc()

            # Check if there's a dimension mismatch
            print("\n[6] Checking for dimension issues...")
            try:
                # Get actual embedding
                cur.execute("""
                    SELECT embedding::text
                    FROM lecture_chunks
                    LIMIT 1
                """)
                result = cur.fetchone()
                if result:
                    emb_str = result[0]
                    # Count commas to estimate dimensions
                    dims = emb_str.count(',') + 1 if emb_str else 0
                    print(f"✓ Sample embedding: ~{dims} dimensions")
                    print(f"  First 100 chars: {emb_str[:100]}...")
            except Exception as e:
                print(f"⚠️  Could not inspect embedding: {e}")

            # Try the actual search query from database.py
            print("\n[7] Testing actual search_similar_chunks query...")
            try:
                # Create a test embedding
                test_vec = '[' + ','.join(['0.1'] * 1536) + ']'

                cur.execute("""
                    SELECT
                        c.id,
                        c.text,
                        l.course_name,
                        1 - (c.embedding <=> %s::vector) as similarity
                    FROM lecture_chunks c
                    JOIN lectures l ON c.lecture_id = l.id
                    WHERE 1=1
                    ORDER BY c.embedding <=> %s::vector
                    LIMIT 5
                """, [test_vec, test_vec])

                results = cur.fetchall()
                print(f"✓ Query executed, returned {len(results)} results")

                if len(results) == 0:
                    print("\n❌ QUERY RETURNS 0 RESULTS!")
                    print("   This is the core issue.")
                else:
                    print("\n✓ Results:")
                    for row in results:
                        chunk_id, text, course, sim = row
                        print(f"    - {course}: sim={sim:.4f}, text={text[:50]}...")

            except Exception as e:
                print(f"❌ Search query failed: {e}")
                import traceback
                traceback.print_exc()

    finally:
        db._put_conn(conn)

    print("\n" + "="*80)
    print("PGVECTOR CHECK COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()
