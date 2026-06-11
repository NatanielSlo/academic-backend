import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
import httpx
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from app.config import config

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when LLM operations fail."""
    pass


class LLMService:
    """Service for LLM operations using DeepSeek API."""

    def __init__(self):
        self.provider = config.llm.provider
        self.api_key = config.llm.api_key
        self.simple_model = config.llm.models["simple"]  # deepseek-v4-flash
        self.complex_model = config.llm.models["complex"]  # deepseek-v4-pro

        # DeepSeek API endpoint
        self.base_url = "https://api.deepseek.com/v1"

        # Create logs directory
        self.logs_dir = Path("logs/llm")
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized LLM service (provider={self.provider}, simple={self.simple_model}, complex={self.complex_model})")

    def _load_prompt(self, prompt_file: str) -> str:
        """Load prompt template from file."""
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / prompt_file
        if not prompt_path.exists():
            raise LLMError(f"Prompt file not found: {prompt_path}")

        return prompt_path.read_text(encoding="utf-8")

    def _log_request(self, chunk_id: int, prompt: str, response: str, duration: float):
        """Log LLM request/response to file for inspection."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.logs_dir / f"chunk_{chunk_id:03d}_{timestamp}.json"

        log_data = {
            "chunk_id": chunk_id,
            "timestamp": timestamp,
            "duration_seconds": round(duration, 2),
            "input_length": len(prompt),
            "output_length": len(response),
            "input": prompt[:500] + "..." if len(prompt) > 500 else prompt,  # First 500 chars
            "output": response,
            "full_input_preview": prompt[:2000]  # More context for debugging
        }

        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)

    def _save_checkpoint(self, cleaned_chunks: List[Dict[str, Any]]) -> Path:
        """Save cleaned chunks checkpoint for resume capability."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        checkpoint_file = self.logs_dir / f"cleaned_chunks_{timestamp}.json"

        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(cleaned_chunks, f, indent=2, ensure_ascii=False)

        return checkpoint_file

    @staticmethod
    def load_checkpoint(checkpoint_file: Path) -> List[Dict[str, Any]]:
        """Load cleaned chunks from checkpoint file."""
        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: str = "simple",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        log_id: Optional[int] = None,
        json_mode: bool = False,
        return_finish_reason: bool = False
    ):
        """
        Generate completion using DeepSeek API.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            model: "simple" (flash) or "complex" (pro)
            temperature: Sampling temperature (0-1)
            max_tokens: Max tokens to generate
            return_finish_reason: If True, return (text, finish_reason) tuple.
                finish_reason == "length" means the output was truncated by max_tokens.

        Returns:
            Generated text, or (text, finish_reason) if return_finish_reason=True

        Raises:
            LLMError: If completion fails
        """
        model_name = self.simple_model if model == "simple" else self.complex_model
        start_time = time.time()

        try:
            messages = []

            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt
                })

            messages.append({
                "role": "user",
                "content": prompt
            })

            # Call DeepSeek API
            # Use longer timeout for large requests (especially outline generation)
            timeout_seconds = 300.0 if max_tokens > 4096 else 120.0

            # Build request payload
            request_json = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }

            # Add JSON mode if requested
            if json_mode:
                request_json["response_format"] = {"type": "json_object"}

            with httpx.Client(timeout=timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json=request_json
                )

                response.raise_for_status()
                result = response.json()

                choice = result["choices"][0]
                completion = choice["message"]["content"]
                finish_reason = choice.get("finish_reason")
                duration = time.time() - start_time

                logger.debug(f"LLM completion: {len(completion)} chars in {duration:.2f}s (finish_reason={finish_reason})")

                # Truncation is the #1 cause of unparseable JSON downstream.
                # Surface it loudly instead of letting json.loads fail cryptically later.
                if finish_reason == "length":
                    logger.warning(
                        f"LLM output TRUNCATED (finish_reason=length): hit max_tokens={max_tokens} "
                        f"on model={model_name}. Output is likely incomplete/invalid JSON."
                    )

                # Log request/response if log_id provided
                if log_id is not None:
                    self._log_request(log_id, prompt, completion, duration)

                if return_finish_reason:
                    return completion, finish_reason
                return completion

        except httpx.HTTPStatusError as e:
            error_msg = f"DeepSeek API error: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            raise LLMError(error_msg)
        except Exception as e:
            error_msg = f"LLM completion failed: {str(e)}"
            logger.error(error_msg)
            raise LLMError(error_msg)

    def clean_transcript(
        self,
        raw_transcript: str,
        show_progress: bool = True
    ) -> str:
        """
        Clean up raw transcript using LLM.

        Removes filler words, fixes repetitions, improves punctuation,
        corrects technical terms.

        Args:
            raw_transcript: Raw transcript text
            show_progress: Whether to print progress

        Returns:
            Cleaned transcript

        Raises:
            LLMError: If cleanup fails
        """
        try:
            if show_progress:
                print(f"\n[LLM] Cleaning transcript ({len(raw_transcript)} chars)...")

            # Load prompt template
            prompt_template = self._load_prompt("transcript_cleanup.txt")

            # Combine template with actual transcript
            full_prompt = prompt_template + "\n\n" + raw_transcript

            # Call LLM
            cleaned = self.complete(
                prompt=full_prompt,
                model="simple",  # Use fast model for cleanup
                temperature=0.1,  # Low temperature for consistency
                max_tokens=len(raw_transcript) * 2  # Allow some expansion
            )

            if show_progress:
                print(f"[LLM] ✓ Cleaned transcript ({len(cleaned)} chars)")

            return cleaned.strip()

        except Exception as e:
            error_msg = f"Transcript cleanup failed: {str(e)}"
            logger.error(error_msg)
            raise LLMError(error_msg)

    def clean_transcript_chunks(
        self,
        chunks: List[Dict[str, Any]],
        text_key: str = "text",
        show_progress: bool = True,
        max_workers: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Clean transcript chunks with parallel processing.

        This processes chunks in parallel to speed up processing significantly.

        Args:
            chunks: List of chunk dicts
            text_key: Key containing the text to clean
            show_progress: Whether to print progress
            max_workers: Number of parallel workers (default: 5)

        Returns:
            Chunks with cleaned text (in original order)

        Raises:
            LLMError: If cleanup fails
        """
        if not chunks:
            return []

        try:
            if show_progress:
                print(f"\n{'='*60}")
                print(f"Cleaning {len(chunks)} transcript chunks with LLM")
                print(f"Model: {self.simple_model}")
                print(f"Parallel workers: {max_workers}")
                print(f"Logs directory: {self.logs_dir}")
                print(f"{'='*60}\n")

            # Load prompt template once
            prompt_template = self._load_prompt("transcript_cleanup.txt")

            start_time = time.time()
            completed = 0
            cleaned_chunks_dict = {}  # Store by index to maintain order

            def clean_single_chunk(i: int, chunk: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
                """Clean a single chunk (for parallel execution)."""
                raw_text = chunk[text_key].strip()

                # Skip if chunk is already empty
                if not raw_text:
                    logger.warning(f"Chunk {i} is empty - skipping LLM cleanup")
                    return i, chunk

                # Combine template with chunk text
                full_prompt = prompt_template + "\n\n" + raw_text

                max_retries = 2
                cleaned_text = None

                for attempt in range(max_retries):
                    try:
                        # Clean the chunk with logging
                        cleaned_text = self.complete(
                            prompt=full_prompt,
                            model="simple",
                            temperature=0.1,
                            max_tokens=len(raw_text) * 2,
                            log_id=i if attempt == 0 else None  # Log only first attempt
                        ).strip()

                        # If LLM returned empty string, retry
                        if not cleaned_text:
                            logger.warning(f"Chunk {i} - LLM returned empty string (attempt {attempt + 1}/{max_retries})")
                            if attempt < max_retries - 1:
                                time.sleep(1)  # Wait before retry
                                continue
                        else:
                            break  # Success

                    except Exception as e:
                        logger.error(f"Chunk {i} - LLM error on attempt {attempt + 1}: {e}")
                        if attempt < max_retries - 1:
                            time.sleep(1)
                            continue
                        else:
                            raise

                # Fallback: if still empty after retries, use original text
                if not cleaned_text:
                    logger.warning(f"Chunk {i} - LLM failed to clean after {max_retries} attempts, using original text")
                    cleaned_text = raw_text

                # Create new chunk with cleaned text
                cleaned_chunk = chunk.copy()
                cleaned_chunk[text_key] = cleaned_text

                return i, cleaned_chunk

            # Process chunks in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_index = {
                    executor.submit(clean_single_chunk, i, chunk): i
                    for i, chunk in enumerate(chunks)
                }

                # Process as they complete
                for future in as_completed(future_to_index):
                    i, cleaned_chunk = future.result()
                    cleaned_chunks_dict[i] = cleaned_chunk
                    completed += 1

                    if show_progress:
                        elapsed = time.time() - start_time
                        avg_time = elapsed / completed
                        remaining = len(chunks) - completed
                        eta = avg_time * remaining

                        print(f"[LLM] {completed}/{len(chunks)} chunks | "
                              f"Avg: {avg_time:.1f}s/chunk | "
                              f"ETA: {eta:.0f}s ({eta/60:.1f}m)")

            # Reconstruct in original order
            cleaned_chunks = [cleaned_chunks_dict[i] for i in range(len(chunks))]

            if show_progress:
                total_time = time.time() - start_time
                print(f"\n[SUCCESS] Cleaned {len(cleaned_chunks)} chunks in {total_time:.1f}s ({total_time/60:.1f}m)")
                print(f"  Average: {total_time/len(chunks):.1f}s per chunk")
                print(f"  Speedup: ~{len(chunks)/(total_time/10):.1f}x vs sequential")

            # Save checkpoint for resume capability
            checkpoint_file = self._save_checkpoint(cleaned_chunks)
            if show_progress:
                print(f"  Checkpoint saved: {checkpoint_file}")

            return cleaned_chunks

        except Exception as e:
            error_msg = f"Chunk cleanup failed: {str(e)}"
            logger.error(error_msg)
            raise LLMError(error_msg)


# Test script
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    service = LLMService()

    # Test transcript cleanup
    sample_transcript = """
    Um, so today we're gonna talk about, uh, dynamic programming. So, like, dynamic programming
    is, um, you know, it's a method for solving, like, complex problems by, uh, breaking them
    down into, um, simpler subproblems. So, like, let's start with the, uh, the Fibonacci
    sequence example, okay?
    """

    print("Original transcript:")
    print(sample_transcript)
    print("\n" + "="*60 + "\n")

    cleaned = service.clean_transcript(sample_transcript)

    print("Cleaned transcript:")
    print(cleaned)
