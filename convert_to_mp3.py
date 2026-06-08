#!/usr/bin/env python3
"""Convert mp4 to mp3 for transcription."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.audio_converter import AudioConverter, AudioConversionError


def main():
    # Input mp4 file
    input_file = Path("downloads/audio/bea4419d-2cb0-4cb7-883a-b0446582c448.mp4")

    if not input_file.exists():
        print(f"[ERROR] File not found: {input_file}")
        print("Available files:")
        for f in Path("downloads/audio").glob("*.mp4"):
            print(f"  - {f.name}")
        return

    converter = AudioConverter()

    try:
        # Check ffmpeg
        if not converter.check_ffmpeg():
            print("[ERROR] ffmpeg not found!")
            print("\nInstall ffmpeg:")
            print("  Windows: https://www.gyan.dev/ffmpeg/builds/")
            print("  Or: choco install ffmpeg")
            print("  Or: pip install ffmpeg-python (just the wrapper)")
            return

        # Convert with lower bitrate for smaller file
        output_file = converter.convert_to_mp3(
            input_file,
            bitrate="64k"  # Lower bitrate = smaller file, still good for speech
        )

        print(f"\n{'='*60}")
        print("Ready for transcription!")
        print(f"File: {output_file}")
        print(f"{'='*60}\n")

    except AudioConversionError as e:
        print(f"[FAIL] {e}")
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
