import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AudioConversionError(Exception):
    """Raised when audio conversion fails."""
    pass


class AudioConverter:
    """Service for converting audio files."""

    @staticmethod
    def check_ffmpeg() -> bool:
        """Check if ffmpeg is available."""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                check=True
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def convert_to_mp3(
        self,
        input_path: Path,
        output_path: Optional[Path] = None,
        bitrate: str = "128k"
    ) -> Path:
        """
        Convert audio/video file to MP3.

        Args:
            input_path: Path to input file (mp4, m4a, etc.)
            output_path: Path for output MP3 (default: same name with .mp3)
            bitrate: MP3 bitrate (default: 128k for smaller files)

        Returns:
            Path to converted MP3 file

        Raises:
            AudioConversionError: If conversion fails
        """
        if not input_path.exists():
            raise AudioConversionError(f"Input file not found: {input_path}")

        if not self.check_ffmpeg():
            raise AudioConversionError(
                "ffmpeg not found. Please install: https://www.gyan.dev/ffmpeg/builds/"
            )

        # Default output path
        if output_path is None:
            output_path = input_path.with_suffix('.mp3')

        print(f"\n{'='*60}")
        print(f"Converting to MP3")
        print(f"Input:  {input_path.name} ({input_path.stat().st_size / 1024 / 1024:.2f} MB)")
        print(f"Output: {output_path.name}")
        print(f"Bitrate: {bitrate}")
        print(f"{'='*60}\n")

        # ffmpeg command for MP3 conversion
        cmd = [
            "ffmpeg",
            "-i", str(input_path),
            "-vn",  # No video
            "-ar", "44100",  # Sample rate
            "-ac", "2",  # Stereo
            "-b:a", bitrate,  # Bitrate
            "-y",  # Overwrite output file
            str(output_path)
        ]

        try:
            logger.info(f"Converting {input_path} to MP3")
            print("[INFO] Converting... (this may take a minute)")

            # Run ffmpeg with real-time output
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                universal_newlines=True
            )

            # Show progress
            for line in process.stdout:
                # ffmpeg outputs progress to stderr, which we redirected to stdout
                if "time=" in line:
                    # Extract time progress
                    print(f"\r{line.strip()}", end='', flush=True)

            return_code = process.wait()

            if return_code != 0:
                raise AudioConversionError(f"ffmpeg failed with exit code {return_code}")

            print(f"\n\n[SUCCESS] Converted to MP3!")
            print(f"Output size: {output_path.stat().st_size / 1024 / 1024:.2f} MB")
            print(f"Compression: {output_path.stat().st_size / input_path.stat().st_size * 100:.1f}% of original")

            return output_path

        except KeyboardInterrupt:
            if process:
                process.terminate()
            raise AudioConversionError("Conversion interrupted by user")
        except Exception as e:
            error_msg = f"Conversion failed: {str(e)}"
            logger.error(error_msg)
            raise AudioConversionError(error_msg)
