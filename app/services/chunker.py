import logging
from typing import List, Dict, Any
import tiktoken

from app.config import config

logger = logging.getLogger(__name__)


class ChunkingError(Exception):
    """Raised when text chunking fails."""
    pass


class TextChunker:
    """Service for chunking text into overlapping segments for embedding."""

    def __init__(self):
        self.chunk_size = config.chunking.chunk_size  # tokens
        self.overlap = config.chunking.overlap  # tokens
        self.encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
        logger.info(f"Initialized chunker (size={self.chunk_size}, overlap={self.overlap})")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.encoding.encode(text))

    def chunk_transcript(
        self,
        segments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Chunk transcript segments into token-sized chunks with overlap.

        Args:
            segments: List of transcript segments with keys:
                      - start: start time in seconds
                      - end: end time in seconds
                      - text: transcript text

        Returns:
            List of chunks with keys:
                - chunk_index: index of chunk
                - text: chunk text
                - start_timestamp_seconds: start time of first segment in chunk
                - end_timestamp_seconds: end time of last segment in chunk
                - token_count: number of tokens in chunk
        """
        if not segments:
            raise ChunkingError("No segments provided for chunking")

        chunks = []
        current_chunk = {
            "texts": [],
            "start": None,
            "end": None,
            "tokens": 0
        }

        for segment in segments:
            segment_text = segment["text"].strip()
            if not segment_text:
                continue

            segment_tokens = self.count_tokens(segment_text)

            # Check if adding this segment would exceed chunk size
            if current_chunk["tokens"] + segment_tokens > self.chunk_size and current_chunk["texts"]:
                # Finalize current chunk
                chunk_text = " ".join(current_chunk["texts"])
                chunks.append({
                    "chunk_index": len(chunks),
                    "text": chunk_text,
                    "start_timestamp_seconds": int(current_chunk["start"]),
                    "end_timestamp_seconds": int(current_chunk["end"]),
                    "token_count": current_chunk["tokens"]
                })

                # Start new chunk with overlap
                # Keep last N segments to create overlap
                overlap_text = self._create_overlap(current_chunk["texts"])
                overlap_tokens = self.count_tokens(overlap_text) if overlap_text else 0

                current_chunk = {
                    "texts": [overlap_text] if overlap_text else [],
                    "start": segment["start"],
                    "end": segment["end"],
                    "tokens": overlap_tokens
                }

            # Add segment to current chunk
            if current_chunk["start"] is None:
                current_chunk["start"] = segment["start"]

            current_chunk["texts"].append(segment_text)
            current_chunk["end"] = segment["end"]
            current_chunk["tokens"] += segment_tokens

        # Add final chunk if not empty
        if current_chunk["texts"]:
            chunk_text = " ".join(current_chunk["texts"])
            chunks.append({
                "chunk_index": len(chunks),
                "text": chunk_text,
                "start_timestamp_seconds": int(current_chunk["start"]),
                "end_timestamp_seconds": int(current_chunk["end"]),
                "token_count": current_chunk["tokens"]
            })

        logger.info(f"Created {len(chunks)} chunks from {len(segments)} segments")

        return chunks

    def _create_overlap(self, texts: List[str]) -> str:
        """
        Create overlap text from end of previous chunk.

        Takes text from the end of the chunk until reaching overlap token limit.
        """
        if not texts:
            return ""

        # Start from the end and work backwards
        overlap_texts = []
        tokens = 0

        for text in reversed(texts):
            text_tokens = self.count_tokens(text)

            if tokens + text_tokens > self.overlap:
                break

            overlap_texts.insert(0, text)
            tokens += text_tokens

        return " ".join(overlap_texts)

    def chunk_text(self, text: str) -> List[str]:
        """
        Simple text chunking (no timestamps).

        Args:
            text: Input text

        Returns:
            List of text chunks
        """
        tokens = self.encoding.encode(text)
        chunks = []

        start = 0
        while start < len(tokens):
            end = min(start + self.chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = self.encoding.decode(chunk_tokens)
            chunks.append(chunk_text)

            # Move forward by (chunk_size - overlap) to create overlap
            start += self.chunk_size - self.overlap

        logger.info(f"Created {len(chunks)} chunks from text ({len(tokens)} tokens)")
        return chunks


# Test script
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    chunker = TextChunker()

    # Test with sample transcript
    sample_segments = [
        {"start": 0.0, "end": 5.0, "text": "Hello everyone, today we'll discuss dynamic programming."},
        {"start": 5.0, "end": 10.0, "text": "Dynamic programming is a method for solving complex problems."},
        {"start": 10.0, "end": 15.0, "text": "It breaks them down into simpler subproblems."},
        {"start": 15.0, "end": 20.0, "text": "Let's start with the Fibonacci sequence example."},
    ]

    chunks = chunker.chunk_transcript(sample_segments)

    print(f"\n✓ Created {len(chunks)} chunks:\n")
    for chunk in chunks:
        print(f"Chunk {chunk['chunk_index']}:")
        print(f"  Time: {chunk['start_timestamp_seconds']}s - {chunk['end_timestamp_seconds']}s")
        print(f"  Tokens: {chunk['token_count']}")
        print(f"  Text: {chunk['text'][:100]}...")
        print()
