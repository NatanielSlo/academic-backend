import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
import httpx
from openai import OpenAI
from groq import Groq
import sys
import io
import subprocess
import tempfile
import shutil

from app.config import config

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Raised when transcription fails."""
    pass


class TranscriptionService:
    """Service for transcribing audio using Whisper API (OpenAI or Groq)."""

    # API file size limits (in MB)
    MAX_FILE_SIZE = {
        "groq": 25,  # Groq has 25MB limit
        "openai": 25  # OpenAI also has 25MB limit
    }

    # Chunk duration in seconds (10 minutes = good balance)
    CHUNK_DURATION_SECONDS = 600

    def __init__(self):
        self.provider = config.transcription.provider

        if self.provider == "groq":
            self.client = Groq(
                api_key=config.groq.api_key,
                timeout=600.0  # 10 minutes timeout for large files
            )
            self.model = config.groq.whisper_model
        elif self.provider == "openai":
            self.client = OpenAI(
                api_key=config.openai.api_key,
                timeout=600.0  # 10 minutes timeout for large files
            )
            self.model = config.openai.whisper_model
        else:
            raise ValueError(f"Unknown transcription provider: {self.provider}")

        logger.info(f"Initialized transcription service with provider: {self.provider}")

    def transcribe(
        self,
        audio_path: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        language: Optional[str] = None,
        chunk_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Transcribe audio file using OpenAI Whisper API with chunking for large files.

        Args:
            audio_path: Path to the audio/video file
            progress_callback: Optional callback function(bytes_uploaded, total_bytes)
            language: Optional language code (e.g., "de" for German, "en" for English)

        Returns:
            Dictionary containing:
                - text: Full transcript
                - segments: List of segments with timestamps
                - language: Detected language

        Raises:
            TranscriptionError: If transcription fails
        """
        if not audio_path.exists():
            raise TranscriptionError(f"Audio file not found: {audio_path}")

        try:
            logger.info(f"Starting transcription for {audio_path}")
            file_size_mb = audio_path.stat().st_size / 1024 / 1024
            max_size = self.MAX_FILE_SIZE[self.provider]

            print(f"\n{'='*60}")
            print(f"Transcribing: {audio_path.name}")
            print(f"Provider: {self.provider.upper()}")
            print(f"Model: {self.model}")
            print(f"File size: {file_size_mb:.2f} MB")
            print(f"{'='*60}\n")

            # Check if we need to chunk the file
            if file_size_mb > max_size:
                print(f"[INFO] File exceeds {max_size} MB limit, splitting into chunks...")
                result = self._transcribe_chunks(audio_path, progress_callback, language, chunk_callback)
            else:
                print(f"[INFO] Uploading to {self.provider.upper()} Whisper API...")
                transcript = self._upload_with_progress(
                    audio_path,
                    audio_path.stat().st_size,
                    progress_callback,
                    language
                )

                # Convert to our format
                # Handle both dict and object formats
                segments = []
                for seg in transcript.segments:
                    if isinstance(seg, dict):
                        segments.append({
                            "id": seg.get("id", len(segments)),
                            "start": seg["start"],
                            "end": seg["end"],
                            "text": seg["text"].strip()
                        })
                    else:
                        segments.append({
                            "id": seg.id,
                            "start": seg.start,
                            "end": seg.end,
                            "text": seg.text.strip()
                        })

                result = {
                    "text": transcript.text,
                    "language": transcript.language,
                    "duration": transcript.duration,
                    "segments": segments
                }

            logger.info(f"Transcription completed successfully")
            print(f"\n[SUCCESS] Transcription completed!")
            print(f"Language detected: {result['language']}")
            print(f"Duration: {result['duration']:.2f} seconds")
            print(f"Total segments: {len(result['segments'])}")

            return result

        except Exception as e:
            error_msg = f"Transcription failed: {str(e)}"
            logger.error(error_msg)
            raise TranscriptionError(error_msg)

    def _upload_with_progress(
        self,
        audio_path: Path,
        file_size: int,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        language: Optional[str] = None
    ):
        """Upload file with progress tracking using httpx."""

        # Create a file wrapper that tracks progress - must inherit from io.IOBase
        class ProgressFile(io.BufferedReader):
            def __init__(self, file_path: Path, total_size: int, callback: Optional[Callable]):
                raw_file = io.FileIO(file_path, 'rb')
                super().__init__(raw_file)
                self.total_size = total_size
                self.callback = callback
                self.bytes_read = 0
                self.last_percent = 0

            def read(self, size: int = -1):
                chunk = super().read(size)
                if chunk:
                    self.bytes_read += len(chunk)

                    # Update progress (cap at 100% because SDK may read file multiple times)
                    current_bytes = min(self.bytes_read, self.total_size)

                    if self.callback:
                        self.callback(current_bytes, self.total_size)
                    else:
                        # Default console progress
                        percent = min(100, int((current_bytes / self.total_size) * 100))
                        if percent > self.last_percent:
                            self.last_percent = percent
                            bar_length = 40
                            filled = int(bar_length * percent / 100)
                            bar = '█' * filled + '░' * (bar_length - filled)
                            mb_uploaded = current_bytes / 1024 / 1024
                            mb_total = self.total_size / 1024 / 1024
                            print(f"\r[UPLOAD] {bar} {percent}% ({mb_uploaded:.1f}/{mb_total:.1f} MB)", end='', flush=True)

                return chunk

        with ProgressFile(audio_path, file_size, progress_callback) as progress_file:
            if self.provider == "groq":
                # Groq API
                kwargs = {
                    "model": self.model,
                    "file": progress_file,
                    "response_format": "verbose_json"
                }
                if language:
                    kwargs["language"] = language

                transcript = self.client.audio.transcriptions.create(**kwargs)
            else:
                # OpenAI API
                kwargs = {
                    "model": self.model,
                    "file": progress_file,
                    "response_format": "verbose_json",
                    "timestamp_granularities": ["segment"]
                }
                if language:
                    kwargs["language"] = language

                transcript = self.client.audio.transcriptions.create(**kwargs)

        print()  # New line after progress bar
        print("[INFO] Processing transcription...")

        return transcript

    def _split_audio_into_chunks(self, audio_path: Path, chunk_duration: int) -> List[Path]:
        """
        Split audio file into chunks using ffmpeg.

        Args:
            audio_path: Path to the audio file
            chunk_duration: Duration of each chunk in seconds

        Returns:
            List of paths to chunk files
        """
        temp_dir = Path(tempfile.mkdtemp(prefix="whisper_chunks_"))
        chunk_paths = []

        try:
            # Get audio duration
            duration_cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path)
            ]

            result = subprocess.run(
                duration_cmd,
                capture_output=True,
                text=True,
                check=True
            )
            total_duration = float(result.stdout.strip())
            num_chunks = int((total_duration / chunk_duration) + 1)

            print(f"[INFO] Audio duration: {total_duration:.1f}s")
            print(f"[INFO] Splitting into {num_chunks} chunks of {chunk_duration}s each...")

            # Split into chunks
            for i in range(num_chunks):
                start_time = i * chunk_duration
                chunk_path = temp_dir / f"chunk_{i:03d}.mp3"

                cmd = [
                    "ffmpeg",
                    "-i", str(audio_path),
                    "-ss", str(start_time),
                    "-t", str(chunk_duration),
                    "-vn",  # No video
                    "-ar", "16000",  # 16kHz sample rate (Whisper optimal)
                    "-ac", "1",  # Mono (smaller files)
                    "-b:a", "64k",  # Low bitrate (good enough for speech)
                    "-y",
                    str(chunk_path)
                ]

                subprocess.run(
                    cmd,
                    capture_output=True,
                    check=True
                )

                chunk_paths.append(chunk_path)
                chunk_size = chunk_path.stat().st_size / 1024 / 1024
                print(f"  ✓ Chunk {i+1}/{num_chunks}: {chunk_path.name} ({chunk_size:.1f} MB)")

            return chunk_paths

        except Exception as e:
            # Cleanup on error
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise TranscriptionError(f"Failed to split audio: {str(e)}")

    def _transcribe_chunks(
        self,
        audio_path: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        language: Optional[str] = None,
        chunk_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Transcribe large audio file by splitting into chunks.

        Args:
            audio_path: Path to the audio file
            progress_callback: Optional progress callback
            language: Optional language code

        Returns:
            Combined transcription result
        """
        chunk_paths = []
        temp_dir = None

        try:
            # Split audio into chunks
            chunk_paths = self._split_audio_into_chunks(
                audio_path,
                self.CHUNK_DURATION_SECONDS
            )
            temp_dir = chunk_paths[0].parent

            # Transcribe each chunk
            all_segments = []
            all_text_parts = []
            time_offset = 0.0
            detected_language = None

            print(f"\n[INFO] Transcribing {len(chunk_paths)} chunks...")

            for i, chunk_path in enumerate(chunk_paths):
                print(f"\n{'─'*60}")
                print(f"Processing chunk {i+1}/{len(chunk_paths)}: {chunk_path.name}")
                print(f"{'─'*60}")

                # Transcribe chunk
                chunk_size = chunk_path.stat().st_size
                transcript = self._upload_with_progress(
                    chunk_path,
                    chunk_size,
                    progress_callback,
                    language
                )

                # Store language from first chunk
                if detected_language is None:
                    detected_language = transcript.language

                # Add text
                all_text_parts.append(transcript.text)

                # Add segments with time offset
                # Handle both dict and object formats
                for seg in transcript.segments:
                    if isinstance(seg, dict):
                        start = seg["start"]
                        end = seg["end"]
                        text = seg["text"]
                    else:
                        start = seg.start
                        end = seg.end
                        text = seg.text

                    all_segments.append({
                        "id": len(all_segments),
                        "start": start + time_offset,
                        "end": end + time_offset,
                        "text": text.strip()
                    })

                # Update time offset for next chunk
                time_offset += transcript.duration

                print(f"  ✓ Chunk {i+1} completed ({len(transcript.segments)} segments)")

                if chunk_callback:
                    chunk_callback(i + 1, len(chunk_paths))

            # Combine results
            result = {
                "text": " ".join(all_text_parts),
                "language": detected_language,
                "duration": time_offset,
                "segments": all_segments
            }

            return result

        finally:
            # Cleanup temporary chunk files
            if temp_dir and temp_dir.exists():
                print(f"\n[INFO] Cleaning up temporary chunks...")
                shutil.rmtree(temp_dir, ignore_errors=True)

    def format_transcript_with_timestamps(
        self,
        segments: List[Dict[str, Any]],
        interval_seconds: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Format transcript segments into chunks with timestamps at regular intervals.

        Args:
            segments: List of transcript segments from Whisper
            interval_seconds: How often to create timestamp markers (default: 60s)

        Returns:
            List of formatted transcript entries with timestamps
        """
        formatted = []
        current_text = []
        current_start = 0
        last_timestamp = 0

        for segment in segments:
            start = segment["start"]
            text = segment["text"]

            # Check if we should create a new timestamp entry
            if start - last_timestamp >= interval_seconds:
                # Save previous accumulated text if any
                if current_text:
                    formatted.append({
                        "timestamp": self._format_time(current_start),
                        "timestamp_seconds": int(current_start),
                        "text": " ".join(current_text).strip()
                    })
                    current_text = []

                # Start new entry
                current_start = start
                last_timestamp = start

            current_text.append(text)

        # Add remaining text
        if current_text:
            formatted.append({
                "timestamp": self._format_time(current_start),
                "timestamp_seconds": int(current_start),
                "text": " ".join(current_text).strip()
            })

        return formatted

    def _format_time(self, seconds: float) -> str:
        """Convert seconds to HH:MM:SS format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
