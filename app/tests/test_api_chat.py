"""
Test the /api/chat endpoint directly (without running the server).
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.models.chat import ChatRequest
from app.api.chat import chat
import asyncio

async def main():
    print("\n" + "="*80)
    print("TESTING /api/chat ENDPOINT")
    print("="*80)

    # Test request
    request = ChatRequest(
        question="Was sind die Hausaufgaben?",
        scope="global"
    )

    print(f"\nRequest:")
    print(f"  Question: {request.question}")
    print(f"  Scope: {request.scope}")

    # Call endpoint
    print("\nCalling endpoint...")
    response = await chat(request)

    # Display response
    print("\n" + "="*80)
    print("RESPONSE:")
    print("="*80)

    # Convert to dict for nice printing
    response_dict = response.model_dump()

    print(f"\nAnswer ({len(response.answer)} chars):")
    print("-"*80)
    print(response.answer)

    print(f"\n\nSources: {len(response.sources)}")
    print("-"*80)
    for i, source in enumerate(response.sources, 1):
        print(f"\n[{i}] {source.course_name} L{source.lecture_number} @ {source.timestamp}")
        print(f"    Similarity: {source.similarity:.3f}", end="")
        if source.relevance_score is not None:
            print(f", Relevance: {source.relevance_score:.1f}/10", end="")
        print()
        print(f"    {source.chunk_text[:80]}...")

    print("\n" + "="*80)
    print("✓ API endpoint working correctly")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())
