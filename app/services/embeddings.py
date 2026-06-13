import logging
from typing import List, Callable, Optional
from openai import OpenAI
import time

from app.config import config

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""
    pass


class EmbeddingService:
    """Service for generating text embeddings using OpenAI."""

    def __init__(self):
        self.client = OpenAI(api_key=config.openai.api_key)
        self.model = config.openai.embedding_model
        logger.info(f"Initialized embedding service with model: {self.model}")

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text

        Returns:
            Embedding vector (1536 dimensions for text-embedding-3-small)

        Raises:
            EmbeddingError: If embedding generation fails
        """
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text
            )
            embedding = response.data[0].embedding
            logger.debug(f"Generated embedding for text ({len(text)} chars)")
            return embedding

        except Exception as e:
            error_msg = f"Failed to generate embedding: {str(e)}"
            logger.error(error_msg)
            raise EmbeddingError(error_msg)

    def embed_batch(
        self,
        texts: List[str],
        show_progress: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches.

        OpenAI allows up to 2048 texts per request, but we use smaller batches
        to avoid rate limits and provide progress feedback.

        Args:
            texts: List of input texts
            show_progress: Whether to print progress

        Returns:
            List of embedding vectors

        Raises:
            EmbeddingError: If embedding generation fails
        """
        if not texts:
            return []

        batch_size = 100  # Process 100 at a time
        all_embeddings = []

        try:
            total_batches = (len(texts) + batch_size - 1) // batch_size

            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                batch_num = i // batch_size + 1

                if show_progress:
                    print(f"[EMBEDDING] Batch {batch_num}/{total_batches} ({len(batch)} texts)...", end='', flush=True)

                # Generate embeddings for batch
                response = self.client.embeddings.create(
                    model=self.model,
                    input=batch
                )

                # Extract embeddings in order
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)

                if show_progress:
                    print(" ✓")

                if progress_callback:
                    progress_callback(batch_num, total_batches)

                # Rate limiting: small delay between batches
                if i + batch_size < len(texts):
                    time.sleep(0.1)

            logger.info(f"Generated {len(all_embeddings)} embeddings in {total_batches} batches")
            return all_embeddings

        except Exception as e:
            error_msg = f"Failed to generate batch embeddings: {str(e)}"
            logger.error(error_msg)
            raise EmbeddingError(error_msg)

    def embed_chunks(
        self,
        chunks: List[dict],
        text_key: str = "text",
        show_progress: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[dict]:
        """
        Generate embeddings for a list of chunk dictionaries.

        Args:
            chunks: List of chunk dicts (must contain text_key field)
            text_key: Key in chunk dict containing the text to embed
            show_progress: Whether to print progress

        Returns:
            List of chunks with 'embedding' field added (empty chunks are filtered out)

        Raises:
            EmbeddingError: If embedding generation fails
        """
        if not chunks:
            return []

        try:
            # Extract texts
            texts = [chunk[text_key].strip() for chunk in chunks]

            # Validate no empty texts (should be prevented by LLM service)
            empty_indices = [i for i, text in enumerate(texts) if not text]
            if empty_indices:
                raise EmbeddingError(f"Found {len(empty_indices)} empty chunks at indices {empty_indices}. "
                                    "This should not happen - LLM cleanup should use fallback for empty results.")

            if show_progress:
                print(f"\n{'='*60}")
                print(f"Generating embeddings for {len(texts)} chunks")
                print(f"Model: {self.model}")
                print(f"{'='*60}\n")

            # Generate embeddings
            embeddings = self.embed_batch(
                texts,
                show_progress=show_progress,
                progress_callback=progress_callback
            )

            # Add embeddings to chunks
            for chunk, embedding in zip(chunks, embeddings):
                chunk['embedding'] = embedding

            if show_progress:
                print(f"\n[SUCCESS] Generated {len(embeddings)} embeddings")

            return chunks

        except Exception as e:
            error_msg = f"Failed to embed chunks: {str(e)}"
            logger.error(error_msg)
            raise EmbeddingError(error_msg)


# Test script
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    service = EmbeddingService()

    # Test single embedding
    print("Testing single text embedding...")
    text = "Dynamic programming is a method for solving complex problems."
    embedding = service.embed_text(text)
    print(f"✓ Generated embedding with {len(embedding)} dimensions\n")

    # Test batch embedding
    print("Testing batch embedding...")
    texts = [
        "Hello world",
        "This is a test",
        "Embeddings are useful for semantic search"
    ]
    embeddings = service.embed_batch(texts, show_progress=True)
    print(f"✓ Generated {len(embeddings)} embeddings\n")

    # Test chunk embedding
    print("Testing chunk embedding...")
    chunks = [
        {"text": "First chunk", "index": 0},
        {"text": "Second chunk", "index": 1}
    ]
    chunks_with_embeddings = service.embed_chunks(chunks, show_progress=True)
    print(f"✓ All chunks now have embeddings: {all('embedding' in c for c in chunks_with_embeddings)}")
