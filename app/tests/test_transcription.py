#!/usr/bin/env python3
"""Test script for Whisper transcription."""

import sys
from pathlib import Path
import json

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.transcription import TranscriptionService, TranscriptionError


def test_transcription(language=None):
    """
    Test transcription with existing audio file.

    Args:
        language: Language code (e.g., "de", "en") or None for auto-detect
    """

    # Use the mp4 file we already downloaded
    audio_file = Path("downloads/audio/bea4419d-2cb0-4cb7-883a-b0446582c448.mp3")

    if not audio_file.exists():
        print(f"[ERROR] Audio file not found: {audio_file}")
        print("Please run test_extraction.py first to download a lecture")
        return

    print(f"Testing transcription...")
    print(f"File: {audio_file}")
    if language:
        print(f"Language: {language}")
    else:
        print(f"Language: auto-detect")
    print("-" * 50)

    service = TranscriptionService()

    try:
        # Transcribe with language parameter
        result = service.transcribe(audio_file, language=language)

        print("\n" + "="*60)
        print("TRANSCRIPTION RESULT")
        print("="*60)
        print(f"Language: {result['language']}")
        print(f"Duration: {result['duration']:.2f} seconds ({result['duration']/60:.1f} minutes)")
        print(f"Total segments: {len(result['segments'])}")
        print(f"\nFirst 500 characters of transcript:")
        print("-" * 60)
        print(result['text'][:500] + "...")
        print("-" * 60)

        # Format with timestamps
        formatted = service.format_transcript_with_timestamps(result['segments'], interval_seconds=60)

        print(f"\nFormatted transcript (60s intervals): {len(formatted)} entries")
        print("\nFirst 3 entries:")
        print("-" * 60)
        for entry in formatted[:3]:
            print(f"[{entry['timestamp']}] {entry['text'][:100]}...")
        print("-" * 60)

        # Save to JSON for inspection
        output_file = Path("transcript_output.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({
                "raw_result": result,
                "formatted": formatted
            }, f, indent=2, ensure_ascii=False)

        print(f"\n[SUCCESS] Full transcript saved to: {output_file}")

    except TranscriptionError as e:
        print(f"[FAIL] Transcription failed: {e}")
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Check if language specified in command line
    # Usage: python test_transcription.py de
    #    or: python test_transcription.py en
    #    or: python test_transcription.py (auto-detect)

    language = None
    if len(sys.argv) > 1:
        language = sys.argv[1]

    test_transcription(language=language)
