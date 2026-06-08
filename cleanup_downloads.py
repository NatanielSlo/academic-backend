#!/usr/bin/env python3
"""Cleanup script for incomplete downloads."""

import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import config


def cleanup_incomplete_downloads():
    """Remove all incomplete download files (.part, .ytdl, fragments)."""
    output_dir = Path(config.audio.output_dir)

    if not output_dir.exists():
        print(f"Directory {output_dir} does not exist")
        return

    patterns = ["*.part", "*.ytdl", "*Frag*"]
    removed_count = 0
    removed_size = 0

    for pattern in patterns:
        for file in output_dir.glob(pattern):
            size = file.stat().st_size
            file.unlink()
            removed_count += 1
            removed_size += size
            print(f"Removed: {file.name} ({size / 1024 / 1024:.2f} MB)")

    if removed_count > 0:
        print(f"\nCleaned up {removed_count} files ({removed_size / 1024 / 1024:.2f} MB total)")
    else:
        print("No incomplete files found")


if __name__ == "__main__":
    cleanup_incomplete_downloads()
