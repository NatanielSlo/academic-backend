"""
Export transcript from test_transcription.py result to JSON file.

This creates a JSON file compatible with test_pipeline_from_transcript.py
"""

import json
from pathlib import Path


def export_sample_transcript():
    """Create a sample transcript JSON file."""
    # Example: your actual transcript from test_transcription.py
    # Replace this with your real transcript data
    transcript = {
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 5.5,
                "text": "Um, so hello everyone, uh, welcome to, like, the first lecture of EIDI."
            },
            {
                "id": 1,
                "start": 5.5,
                "end": 12.0,
                "text": "So today we're gonna talk about, um, dynamic programming, okay?"
            },
            # Add more segments here...
        ],
        "language": "en",
        "duration": 12.0
    }

    # Save to file
    output_file = Path("transcript_export.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)

    print(f"✓ Transcript exported to: {output_file}")
    print(f"  Segments: {len(transcript['segments'])}")
    print(f"  Duration: {transcript['duration']}s")
    print(f"\nTo use this transcript, run:")
    print(f"  python test_pipeline_from_transcript.py {output_file}")


def export_from_whisper_result(result_dict):
    """
    Export transcript from Whisper API result.

    Args:
        result_dict: The dict returned from TranscriptionService.transcribe()
                    with keys: text, language, duration, segments
    """
    output_file = Path("transcript_export.json")

    # Extract just what we need
    export_data = {
        "segments": result_dict["segments"],
        "language": result_dict.get("language"),
        "duration": result_dict.get("duration")
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)

    print(f"✓ Transcript exported to: {output_file}")
    print(f"  Segments: {len(export_data['segments'])}")
    print(f"  Duration: {export_data.get('duration')}s")
    print(f"  Language: {export_data.get('language')}")
    print(f"\nTo process this transcript through the pipeline, run:")
    print(f"  python test_pipeline_from_transcript.py {output_file}")


if __name__ == "__main__":
    print("This script helps you export transcripts to JSON format.\n")
    print("Option 1: Edit export_sample_transcript() and paste your transcript data")
    print("Option 2: Use export_from_whisper_result(your_result) in your code")
    print("\nFor now, creating a sample export...")

    export_sample_transcript()
