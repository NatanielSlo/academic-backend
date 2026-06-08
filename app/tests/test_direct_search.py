"""
Test search_similar_chunks directly with same parameters as inspect_embeddings.py
"""

import sys
from pathlib import Path
import logging

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))

from app.services.database import DatabaseService
from app.services.embeddings import EmbeddingService

logging.basicConfig(level=logging.DEBUG)

def main():
    print("\n" + "="*80)
    print("DIRECT SEARCH TEST")
    print("="*80)

    db = DatabaseService()
    emb_service = EmbeddingService()

    # Create test embedding
    print("\n[1] Creating test embedding...")
    question = "Was ist dynamic programming?"
    test_embedding = emb_service.embed_text(question)
    print(f"✓ Embedding created: {len(test_embedding)} dims")
    print(f"  First 5 values: {test_embedding[:5]}")

    # Call search_similar_chunks (the method that returns 0)
    print("\n[2] Calling search_similar_chunks...")
    results = db.search_similar_chunks(
        query_embedding=test_embedding,
        top_k=5,
        lecture_id=None,
        course_name=None
    )

    print(f"\n✓ search_similar_chunks returned: {len(results)} results")

    if results:
        print("\nResults:")
        for i, result in enumerate(results, 1):
            print(f"  [{i}] Similarity: {result['similarity']:.4f}")
            print(f"      Course: {result['course_name']}")
            print(f"      Text: {result['text'][:80]}...")
    else:
        print("\n❌ NO RESULTS!")
        print("\nLet's try manually constructing the same query...")

        conn = db._get_conn()
        try:
            with conn.cursor() as cur:
                embedding_str = '[' + ','.join(map(str, test_embedding)) + ']'

                print(f"\nEmbedding string length: {len(embedding_str)} chars")
                print(f"First 100 chars: {embedding_str[:100]}...")

                # Exact same query as in search_similar_chunks
                query = """
                    SELECT
                        c.id,
                        c.lecture_id,
                        c.text,
                        c.start_timestamp_seconds,
                        c.end_timestamp_seconds,
                        l.course_name,
                        l.lecture_number,
                        l.url,
                        1 - (c.embedding <=> %s::vector) as similarity
                    FROM lecture_chunks c
                    JOIN lectures l ON c.lecture_id = l.id
                    WHERE 1=1
                    ORDER BY c.embedding <=> %s::vector
                    LIMIT %s
                """
                params = [embedding_str, embedding_str, 5]

                print(f"\nExecuting manual query...")
                print(f"Params: embedding_str (twice), top_k=5")

                cur.execute(query, params)
                manual_results = cur.fetchall()

                print(f"\n✓ Manual query returned: {len(manual_results)} results")

                if manual_results:
                    print("\nManual results:")
                    for row in manual_results[:3]:
                        print(f"  - Similarity: {row[8]:.4f}")  # similarity is 9th column
                        print(f"    Course: {row[5]}")  # course_name is 6th column
                        print(f"    Text: {row[2][:80]}...")  # text is 3rd column
                else:
                    print("\n❌ Manual query also returns nothing!")

        finally:
            db._put_conn(conn)

if __name__ == "__main__":
    main()
