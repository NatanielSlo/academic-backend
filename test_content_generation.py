"""
Test script for content generation pipeline.
Tests the three-pass generation with the existing transcript.
"""

import sys
import json
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.content_generator import ContentGenerator, ContentGeneratorError
from app.config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def load_transcript():
    """Load the example transcript."""
    transcript_file = Path(__file__).parent / "transcript_output.json"

    if not transcript_file.exists():
        raise FileNotFoundError(f"Transcript file not found: {transcript_file}")

    with open(transcript_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Extract text from segments
    text = data["raw_result"]["text"]

    logger.info(f"Loaded transcript: {len(text)} chars")
    return text


def main():
    """Run the content generation test."""
    print("="*70)
    print("CONTENT GENERATION PIPELINE TEST")
    print("="*70)

    try:
        # Load transcript
        print("\n[1/4] Loading transcript...")
        full_transcript = load_transcript()

        # Initialize generator
        print("\n[2/4] Initializing content generator...")
        generator = ContentGenerator()

        # Dummy lecture ID for testing
        lecture_id = "test-lecture-001"

        print(f"\nTranscript preview (first 500 chars):")
        print("-" * 70)
        print(full_transcript[:500])
        print("-" * 70)

        # Test Pass 1: Extract outline
        print("\n[3/4] Running Pass 1: Outline Extraction...")
        print("This will use DeepSeek API to analyze the full transcript.")
        print("Model: deepseek-v4-pro (complex)")
        print(f"Estimated tokens: ~{len(full_transcript) // 4}")

        confirm = input("\nProceed with outline extraction? (y/n): ")
        if confirm.lower() != 'y':
            print("Aborted.")
            return

        outline = generator.pass1_extract_outline(
            lecture_id=lecture_id,
            full_transcript=full_transcript,
            show_progress=True
        )

        print("\n✓ Outline extraction complete!")
        print(f"  Topics: {len(outline.get('topics', []))}")
        print(f"  Output saved to: {generator.logs_dir}/outline_{lecture_id}_*.json")

        # Test Pass 2a: Generate notes
        print("\n[4/4] Running Pass 2a: Notes Generation...")
        confirm = input("Proceed with notes generation? (y/n): ")
        if confirm.lower() != 'y':
            print("Skipping notes generation.")
        else:
            notes = generator.pass2_generate_notes(
                lecture_id=lecture_id,
                outline=outline,
                show_progress=True
            )

            print("\n✓ Notes generation complete!")
            print(f"  Length: {len(notes)} chars")
            print(f"  Output saved to: {generator.logs_dir}/notes_{lecture_id}_*.md")

        # Test Pass 2b: Generate quiz
        print("\n[4/4] Running Pass 2b: Quiz Generation...")
        num_questions = input("How many quiz questions? (default: 10): ")
        num_questions = int(num_questions) if num_questions else 10

        quiz = generator.pass2_generate_quiz(
            lecture_id=lecture_id,
            outline=outline,
            num_questions=num_questions,
            show_progress=True
        )

        print("\n✓ Quiz generation complete!")
        print(f"  Questions: {len(quiz.get('questions', []))}")
        print(f"  Output saved to: {generator.logs_dir}/quiz_{lecture_id}_*.json")

        # Test Pass 3: Verify coverage
        if 'notes' in locals():
            print("\n[4/4] Running Pass 3: Coverage Verification...")
            coverage = generator.pass3_verify_coverage(
                lecture_id=lecture_id,
                outline=outline,
                notes=notes,
                quiz=quiz,
                show_progress=True
            )

            print("\n✓ Coverage verification complete!")
            print(f"  Coverage: {coverage.get('overall_assessment', {}).get('coverage_percent', 0)}%")
            print(f"  Quality: {coverage.get('overall_assessment', {}).get('quality_score', 'N/A')}")
            print(f"  Gaps: {len(coverage.get('gaps', []))}")
            print(f"  Output saved to: {generator.logs_dir}/coverage_{lecture_id}_*.json")

        print("\n" + "="*70)
        print("TEST COMPLETE!")
        print("="*70)
        print(f"\nAll outputs saved to: {generator.logs_dir}")
        print("\nYou can now:")
        print("1. Review the generated outline JSON")
        print("2. Read the generated notes Markdown")
        print("3. Inspect the quiz questions")
        print("4. Check the coverage report for gaps")

    except ContentGeneratorError as e:
        logger.error(f"Content generation failed: {e}")
        print(f"\n❌ ERROR: {e}")
        return 1

    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        return 1

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
