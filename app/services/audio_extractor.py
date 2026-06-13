import os
import re
import time
import subprocess
import signal
from pathlib import Path
from typing import Optional, Callable
from urllib.parse import urlparse
import logging

from app.config import config

logger = logging.getLogger(__name__)

# yt-dlp prints download progress like "[download]  45.2% of ~12.34MiB ...".
# With --newline each update is on its own line so we can parse it.
_DOWNLOAD_PCT_RE = re.compile(r"\[download\]\s+([\d.]+)%")


class AudioExtractionError(Exception):
    """Raised when audio extraction fails."""
    pass


class AudioExtractor:
    """Service for extracting audio from video URLs using yt-dlp."""

    def __init__(self):
        self.output_dir = Path(config.audio.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.allowed_domains = config.audio.allowed_domains

    def validate_url(self, url: str) -> bool:
        """Validate that URL is from an allowed domain."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc

            # Check if domain matches any allowed domain
            for allowed in self.allowed_domains:
                if domain == allowed or domain.endswith(f".{allowed}"):
                    return True

            logger.warning(f"URL domain {domain} not in allowed list: {self.allowed_domains}")
            return False
        except Exception as e:
            logger.error(f"Error parsing URL {url}: {e}")
            return False

    def extract_audio(
        self,
        url: str,
        lecture_id: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Path:
        """
        Extract audio from video URL using yt-dlp.

        Args:
            url: The video URL to extract audio from
            lecture_id: Unique identifier for the lecture (used in filename)
            progress_callback: Optional callback(percent, phase) invoked as the
                download proceeds. `percent` is the download percentage (0-100),
                `phase` is either "downloading" or "converting". Throttled to at
                most ~1 update/second so we don't hammer the database.

        Returns:
            Path to the extracted audio file

        Raises:
            AudioExtractionError: If extraction fails
        """
        if not self.validate_url(url):
            raise AudioExtractionError(f"URL domain not allowed: {url}")

        output_path = self.output_dir / f"{lecture_id}.mp3"

        # yt-dlp command for audio-only extraction
        # TUM streams don't have separate audio - download full stream and extract
        # -f worst: Download lowest quality video (saves bandwidth, we only need audio anyway)
        # -x: Extract audio from video
        # --audio-format mp3: MP3 format optimized for Whisper
        # --audio-quality 5: Compression level (0=best, 9=worst; 5=good balance ~128kbps)
        # --concurrent-fragments: Download fragments in parallel
        # --hls-use-mpegts: Better for HLS streams
        # -o: Output template
        cmd = [
            "python", "-m", "yt_dlp",
            "-f", "worst",  # Lowest quality video = fastest download, audio quality stays the same
            "-x",  # Extract audio
            "--audio-format", "mp3",  # MP3 format (smaller files, good for Whisper)
            "--audio-quality", "5",  # ~128kbps (good for speech)
            "--concurrent-fragments", "8",  # Download 8 fragments in parallel
            "--hls-use-mpegts",  # Better for HLS streams
            "--newline",  # Emit each progress update on its own line so we can parse %
            "--no-playlist",
            "-o", str(output_path),
            url
        ]

        process = None
        try:
            logger.info(f"Starting audio extraction for {url}")
            logger.debug(f"Running command: {' '.join(cmd)}")

            # Run yt-dlp with real-time output for progress tracking
            print(f"\n{'='*60}")
            print(f"Starting download: {url}")
            print(f"{'='*60}\n")

            # Start process with process group for proper cleanup
            process = subprocess.Popen(
                cmd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
            )

            # Stream output in real-time, parsing download progress as we go.
            last_emit = 0.0
            last_pct = -1.0
            saw_download = False
            for line in process.stdout:
                print(line, end='')

                if not progress_callback:
                    continue

                match = _DOWNLOAD_PCT_RE.search(line)
                if match:
                    saw_download = True
                    pct = float(match.group(1))
                    now = time.time()
                    # Throttle: emit on >=1% advance or once per second, plus 100%.
                    if pct >= 100.0 or pct - last_pct >= 1.0 or now - last_emit >= 1.0:
                        last_pct = pct
                        last_emit = now
                        progress_callback(pct, "downloading")
                elif saw_download and "[ExtractAudio]" in line:
                    # Download finished; ffmpeg is now transcoding to MP3.
                    progress_callback(100.0, "converting")

            # Wait for completion
            return_code = process.wait()

            if return_code != 0:
                raise AudioExtractionError(f"yt-dlp failed with exit code {return_code}")

            logger.info(f"Audio extraction completed: {output_path}")

            if not output_path.exists():
                raise AudioExtractionError(f"Audio file not created at {output_path}")

            print(f"\n{'='*60}")
            print(f"Download complete!")
            print(f"{'='*60}\n")

            return output_path

        except KeyboardInterrupt:
            error_msg = "Download interrupted by user"
            logger.warning(error_msg)
            if process:
                logger.info("Terminating yt-dlp process...")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("Process didn't terminate, forcing kill...")
                    process.kill()
            raise AudioExtractionError(error_msg)
        except subprocess.CalledProcessError as e:
            error_msg = f"yt-dlp failed with exit code {e.returncode}"
            logger.error(error_msg)
            if process:
                process.kill()
            raise AudioExtractionError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error during audio extraction: {str(e)}"
            logger.error(error_msg)
            if process:
                process.kill()
            raise AudioExtractionError(error_msg)

    def cleanup_audio(self, lecture_id: str) -> bool:
        """
        Delete audio file for a lecture.

        Args:
            lecture_id: The lecture ID

        Returns:
            True if file was deleted, False if file didn't exist
        """
        audio_path = self.output_dir / f"{lecture_id}.mp3"

        try:
            if audio_path.exists():
                audio_path.unlink()
                logger.info(f"Deleted audio file: {audio_path}")
                return True
            else:
                logger.warning(f"Audio file not found: {audio_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting audio file {audio_path}: {e}")
            return False
