"""
Test query preprocessing - translation + optimization.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.rag import RAGService

def main():
    print("\n" + "="*80)
    print("TESTING QUERY PREPROCESSING")
    print("="*80)

    rag = RAGService()

    # Test queries (mixed languages, vague terms)
    test_queries = [
        # English queries
        ("homework", "English - short term"),
        ("When is the exam?", "English - full sentence"),
        ("What is DP?", "English - abbreviation"),

        # German queries (should be expanded)
        ("Was ist Fibonacci?", "German - should add context"),
        ("Praktikum", "German - single word, vague"),

        # Vague/ambiguous
        ("Abgabe", "German - vague (submission of what?)"),
    ]

    print(f"\nConfig: preprocess_query = {rag.preprocess_query}\n")

    for query, description in test_queries:
        print(f"\n{'-'*80}")
        print(f"Test: {description}")
        print(f"Original:  '{query}'")

        # Test preprocessing
        try:
            optimized = rag._preprocess_query(query)
            print(f"Optimized: '{optimized}'")

            # Compare length and language
            if len(optimized) > len(query) * 1.5:
                print("  → Expanded with context ✓")
            if any(word in query.lower() for word in ['what', 'when', 'how', 'is']):
                if any(word in optimized.lower() for word in ['was', 'wann', 'wie', 'ist']):
                    print("  → Translated to German ✓")
        except Exception as e:
            print(f"  ✗ Error: {e}")

    print("\n" + "="*80)
    print("Now testing full RAG pipeline with preprocessing...")
    print("="*80)

    # Test full pipeline
    test_question = "homework"
    print(f"\nQuestion: '{test_question}'")

    result = rag.answer_question(test_question, scope="global")

    print(f"\nOriginal query: {result['question']}")
    if 'optimized_query' in result:
        print(f"Optimized query: {result['optimized_query']}")

    print(f"\nRetrieved {len(result['sources'])} sources")
    if result['sources']:
        print(f"Top similarities: {[s['similarity'] for s in result['sources'][:3]]}")

    print(f"\nAnswer preview: {result['answer'][:200]}...")

if __name__ == "__main__":
    main()
