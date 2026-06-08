#!/usr/bin/env python3
"""Simple test script for audio extraction."""

import sys
from pathlib import Path
from uuid import uuid4

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.audio_extractor import AudioExtractor, AudioExtractionError


def test_extraction():
    """Test audio extraction with a sample URL."""

    # You can replace this with an actual TUM lecture URL
    test_url = "https://live.rbg.tum.de/w/eidi/20838"
    test_id = str(uuid4())

    print(f"Testing audio extraction...")
    print(f"URL: {test_url}")
    print(f"Lecture ID: {test_id}")
    print("-" * 50)

    extractor = AudioExtractor()

    try:
        # Validate URL first
        if not extractor.validate_url(test_url):
            print("[FAIL] URL validation failed")
            return

        print("[OK] URL validated")

        # Extract audio
        print("[INFO] Extracting audio (this may take a few minutes)...")
        audio_path = extractor.extract_audio(test_url, test_id)

        print(f"[SUCCESS] Audio extracted successfully!")
        print(f"File location: {audio_path}")
        print(f"File size: {audio_path.stat().st_size / 1024 / 1024:.2f} MB")

    except AudioExtractionError as e:
        print(f"[FAIL] Extraction failed: {e}")
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")


if __name__ == "__main__":
    test_extraction()
