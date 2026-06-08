"""
Fix embedding column dimensions from vector(3) to vector(1536).

This will:
1. Check current dimension
2. Create a new column with correct dimensions
3. Copy data if possible (or drop and recreate)
4. Recreate the index
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
    print("FIX EMBEDDING COLUMN DIMENSIONS")
    print("="*80)

    db = DatabaseService()
    conn = db._get_conn()

    try:
        with conn.cursor() as cur:
            # Check current state
            print("\n[1] Checking current embedding column...")
            cur.execute("""
                SELECT
                    c.id,
                    vector_dims(c.embedding) as dims
                FROM lecture_chunks c
                LIMIT 1
            """)
            result = cur.fetchone()

            if result:
                chunk_id, current_dims = result
                print(f"✓ Current dimension: {current_dims}")

                if current_dims == 1536:
                    print("✓ Dimensions are already correct (1536)!")
                    print("  No fix needed.")
                    return
                else:
                    print(f"⚠️  Wrong dimensions: {current_dims} (should be 1536)")
            else:
                print("⚠️  No chunks found")

            # Check how many chunks we have
            cur.execute("SELECT COUNT(*) FROM lecture_chunks")
            chunk_count = cur.fetchone()[0]
            print(f"\n[2] Found {chunk_count} chunks in database")

            if chunk_count == 0:
                print("  No data to preserve, can safely recreate column")
            else:
                print(f"  ⚠️  WARNING: {chunk_count} chunks will be DELETED")
                print("  You will need to re-process your lectures after this fix")

            # Ask for confirmation
            print("\n" + "="*80)
            print("THIS WILL:")
            print("  1. Drop the existing embedding column (vector(3))")
            print("  2. Recreate it as vector(1536)")
            print("  3. Drop and recreate the vector index")
            print(f"  4. DELETE all {chunk_count} existing chunks' embeddings")
            print("\nYou will need to re-run the pipeline to regenerate embeddings.")
            print("="*80)

            response = input("\nType 'YES' to proceed: ")

            if response != "YES":
                print("\n❌ Aborted by user")
                return

            # Proceed with fix
            print("\n[3] Dropping old index...")
            try:
                # Drop the index (might not exist)
                cur.execute("""
                    DROP INDEX IF EXISTS lecture_chunks_embedding_idx
                """)
                print("✓ Dropped old index")
            except Exception as e:
                print(f"  (Index might not exist: {e})")

            print("\n[4] Dropping embedding column...")
            cur.execute("""
                ALTER TABLE lecture_chunks
                DROP COLUMN IF EXISTS embedding
            """)
            print("✓ Dropped embedding column")

            print("\n[5] Creating new embedding column with vector(1536)...")
            cur.execute("""
                ALTER TABLE lecture_chunks
                ADD COLUMN embedding vector(1536)
            """)
            print("✓ Created embedding column: vector(1536)")

            print("\n[6] Creating vector similarity index...")
            cur.execute("""
                CREATE INDEX lecture_chunks_embedding_idx
                ON lecture_chunks
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            """)
            print("✓ Created index")

            # Commit changes
            conn.commit()
            print("\n✅ SUCCESS! Embedding column fixed.")

            # Verify
            print("\n[7] Verifying fix...")
            cur.execute("""
                SELECT column_name, udt_name
                FROM information_schema.columns
                WHERE table_name = 'lecture_chunks'
                AND column_name = 'embedding'
            """)
            result = cur.fetchone()

            if result:
                col_name, udt_name = result
                print(f"✓ Column: {col_name}, Type: {udt_name}")

            # Note that all chunks now have NULL embeddings
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(embedding) as with_embedding
                FROM lecture_chunks
            """)
            total, with_emb = cur.fetchone()
            print(f"✓ Chunks: {total} total, {with_emb} with embeddings")

            print("\n" + "="*80)
            print("NEXT STEPS:")
            print("="*80)
            print("Your chunks still exist but have NULL embeddings.")
            print("\nOption 1: Re-process lectures from scratch")
            print("  - Delete lectures and upload again")
            print("\nOption 2: Re-embed existing chunks")
            print("  - Run a script to regenerate embeddings for existing chunks")
            print("  - This would be faster if you have transcripts already")
            print("\nFor now, try uploading a new lecture to test the fix.")
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
