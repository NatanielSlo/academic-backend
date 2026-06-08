import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.services.database import DatabaseService, DatabaseError
from app.services.embeddings import EmbeddingService, EmbeddingError
from app.services.llm import LLMService, LLMError
from app.config import config

logger = logging.getLogger(__name__)


class RAGError(Exception):
    """Raised when RAG operations fail."""
    pass


class RAGServiceImproved:
    """
    Improved RAG Service with:
    - Better logging/diagnostics
    - Optional re-ranking
    - Flexible prompt selection
    - Improved error handling
    """

    def __init__(
        self,
        use_reranking: bool = False,
        prompt_version: str = "v2"
    ):
        self.db = DatabaseService()
        self.embedding_service = EmbeddingService()
        self.llm_service = LLMService()

        # Configuration
        self.top_k = config.rag.top_k
        self.similarity_threshold = config.rag.similarity_threshold
        self.use_reranking = use_reranking
        self.prompt_version = prompt_version

        # If using re-ranking, fetch more chunks initially
        self.initial_k = self.top_k * 3 if use_reranking else self.top_k

        logger.info(
            f"Initialized RAG service (top_k={self.top_k}, threshold={self.similarity_threshold}, "
            f"reranking={use_reranking}, prompt={prompt_version})"
        )

    def answer_question(
        self,
        question: str,
        scope: str = "global",
        scope_id: Optional[str] = None,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """
        Answer a question using RAG.

        Args:
            question: User's question
            scope: "global", "course", or "lecture"
            scope_id: Course name (if scope=course) or lecture UUID (if scope=lecture)
            verbose: If True, include diagnostic info in response

        Returns:
            Dict with:
                - answer: LLM-generated answer
                - sources: List of source chunks used
                - question: Original question
                - scope: Search scope used
                - diagnostics (optional): Diagnostic information

        Raises:
            RAGError: If RAG pipeline fails
        """
        try:
            logger.info(f"Answering question (scope={scope}, scope_id={scope_id}): {question[:100]}...")

            diagnostics = {} if verbose else None

            # Step 1: Embed the question
            question_embedding = self._embed_question(question)
            if verbose:
                diagnostics['embedding_dims'] = len(question_embedding)

            # Step 2: Retrieve relevant chunks
            chunks = self._retrieve_chunks(
                question_embedding,
                scope=scope,
                scope_id=scope_id
            )

            if verbose:
                diagnostics['chunks_retrieved'] = len(chunks)
                diagnostics['similarities'] = [c.get('similarity', 0) for c in chunks]

            # Step 2.5: Optional re-ranking
            if self.use_reranking and chunks:
                logger.info(f"Re-ranking {len(chunks)} chunks...")
                chunks = self._rerank_chunks(question, chunks)
                if verbose:
                    diagnostics['chunks_after_rerank'] = len(chunks)
                    diagnostics['relevance_scores'] = [c.get('relevance_score', 0) for c in chunks]

            if not chunks:
                logger.warning("No relevant chunks found for question")
                response = {
                    "answer": "Diese Information finde ich nicht in den verfügbaren Vorlesungsunterlagen.",
                    "sources": [],
                    "question": question,
                    "scope": scope
                }
                if verbose:
                    response['diagnostics'] = diagnostics
                return response

            # Log retrieved chunks for debugging
            logger.info(f"Using {len(chunks)} chunks with similarities: "
                       f"{[f'{c.get(\"similarity\", 0):.3f}' for c in chunks]}")

            # Step 3: Generate answer using LLM
            answer = self._generate_answer(question, chunks)

            # Step 4: Format sources
            sources = self._format_sources(chunks)

            logger.info(f"Generated answer with {len(sources)} sources")

            response = {
                "answer": answer,
                "sources": sources,
                "question": question,
                "scope": scope
            }

            if verbose:
                response['diagnostics'] = diagnostics

            return response

        except (EmbeddingError, DatabaseError, LLMError) as e:
            error_msg = f"RAG pipeline failed: {str(e)}"
            logger.error(error_msg)
            raise RAGError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error in RAG: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise RAGError(error_msg)

    def _embed_question(self, question: str) -> List[float]:
        """Embed the user's question."""
        logger.debug("Embedding question...")
        embedding = self.embedding_service.embed_text(question)
        logger.debug(f"Question embedded ({len(embedding)} dimensions)")
        return embedding

    def _retrieve_chunks(
        self,
        query_embedding: List[float],
        scope: str,
        scope_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant chunks using vector similarity search.

        Args:
            query_embedding: Query vector
            scope: Search scope
            scope_id: Scope identifier

        Returns:
            List of chunk dicts with metadata
        """
        logger.debug(f"Searching for chunks (scope={scope}, top_k={self.initial_k})...")

        # Map scope to database parameters
        lecture_id = scope_id if scope == "lecture" else None
        course_name = scope_id if scope == "course" else None

        # Search database
        chunks = self.db.search_similar_chunks(
            query_embedding=query_embedding,
            top_k=self.initial_k,
            lecture_id=lecture_id,
            course_name=course_name
        )

        # Log all chunks before filtering
        logger.debug(f"Retrieved {len(chunks)} chunks from DB:")
        for i, chunk in enumerate(chunks[:10], 1):  # Log first 10
            sim = chunk.get('similarity', 0)
            logger.debug(f"  [{i}] sim={sim:.4f} | {chunk.get('text', '')[:80]}...")

        # Filter by similarity threshold
        filtered_chunks = [
            chunk for chunk in chunks
            if chunk.get('similarity', 0) >= self.similarity_threshold
        ]

        logger.info(
            f"Retrieved {len(filtered_chunks)} chunks "
            f"(filtered from {len(chunks)} by threshold={self.similarity_threshold})"
        )

        if len(filtered_chunks) == 0 and len(chunks) > 0:
            logger.warning(
                f"All chunks filtered out! Best similarity was {chunks[0].get('similarity', 0):.4f}. "
                f"Consider lowering threshold from {self.similarity_threshold}"
            )

        return filtered_chunks

    def _rerank_chunks(
        self,
        question: str,
        chunks: List[Dict[str, Any]],
        top_n: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Re-rank chunks using LLM relevance scoring.

        Args:
            question: Original question
            chunks: Retrieved chunks
            top_n: Number of top chunks to keep (default: self.top_k)

        Returns:
            Re-ranked chunks (sorted by relevance)
        """
        if top_n is None:
            top_n = self.top_k

        if not chunks:
            return []

        scored_chunks = []

        for i, chunk in enumerate(chunks):
            text_preview = chunk.get('text', '')[:400]  # First 400 chars

            prompt = f"""Rate the relevance of this text excerpt for answering the given question.
Output ONLY a number from 0-10 where:
- 0 = completely irrelevant
- 5 = somewhat relevant
- 10 = directly answers the question

Question: {question}

Text excerpt:
{text_preview}

Relevance score (0-10):"""

            try:
                response = self.llm_service.complete(
                    prompt=prompt,
                    model="simple",
                    temperature=0.0,
                    max_tokens=5
                ).strip()

                # Extract number
                score = float(response.split()[0])  # Take first token
                score = max(0, min(10, score))  # Clamp to 0-10

                chunk['relevance_score'] = score
                scored_chunks.append(chunk)

                logger.debug(f"Chunk {i+1} relevance: {score}/10")

            except Exception as e:
                logger.warning(f"Failed to score chunk {i+1}: {e}, using similarity as fallback")
                chunk['relevance_score'] = chunk.get('similarity', 0) * 10
                scored_chunks.append(chunk)

        # Sort by relevance score (descending) and take top N
        scored_chunks.sort(key=lambda x: x['relevance_score'], reverse=True)
        top_chunks = scored_chunks[:top_n]

        logger.info(
            f"Re-ranked {len(scored_chunks)} chunks, keeping top {len(top_chunks)} "
            f"(scores: {[c['relevance_score'] for c in top_chunks]})"
        )

        return top_chunks

    def _generate_answer(self, question: str, chunks: List[Dict[str, Any]]) -> str:
        """
        Generate answer using LLM with retrieved context.

        Args:
            question: User's question
            chunks: Retrieved context chunks

        Returns:
            LLM-generated answer
        """
        logger.debug("Generating answer with LLM...")

        # Load RAG prompt template
        prompt_file = f"rag_qa_{self.prompt_version}.txt"
        prompt_template = self._load_prompt(prompt_file)

        # Build context from chunks
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            course = chunk.get('course_name', 'Unknown')
            lecture = chunk.get('lecture_number', 'Unknown')
            timestamp = self._format_timestamp(chunk.get('start_timestamp_seconds', 0))
            text = chunk.get('text', '')

            # Include similarity/relevance in source for context
            sim = chunk.get('similarity', 0)
            rel = chunk.get('relevance_score')
            score_info = f" (Relevanz: {rel}/10)" if rel else f" (Ähnlichkeit: {sim:.2f})"

            context_parts.append(
                f"[Quelle {i}]{score_info} Kurs: {course}, Vorlesung: {lecture}, Zeit: {timestamp}\n{text}"
            )

        context = "\n\n".join(context_parts)

        logger.debug(f"Context: {len(context)} chars from {len(chunks)} sources")

        # Combine template with context and question
        full_prompt = f"""{prompt_template}

KONTEXT AUS VORLESUNGEN:
{context}

FRAGE: {question}

ANTWORT:"""

        # Generate answer
        answer = self.llm_service.complete(
            prompt=full_prompt,
            model="simple",  # Use fast model for Q&A
            temperature=0.3,  # Low temperature for factual answers
            max_tokens=1000
        )

        logger.debug(f"Generated answer ({len(answer)} chars)")

        return answer.strip()

    def _format_sources(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format chunks into source citations."""
        sources = []

        for chunk in chunks:
            source = {
                "lecture_id": str(chunk.get('lecture_id', '')),
                "course_name": chunk.get('course_name'),
                "lecture_number": chunk.get('lecture_number'),
                "timestamp": self._format_timestamp(chunk.get('start_timestamp_seconds', 0)),
                "timestamp_seconds": chunk.get('start_timestamp_seconds', 0),
                "chunk_text": chunk.get('text', '')[:200] + "...",  # Excerpt
                "similarity": round(chunk.get('similarity', 0), 3)
            }

            # Include relevance score if available
            if 'relevance_score' in chunk:
                source['relevance_score'] = round(chunk['relevance_score'], 2)

            sources.append(source)

        return sources

    def _format_timestamp(self, seconds: int) -> str:
        """Convert seconds to HH:MM:SS format."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _load_prompt(self, prompt_file: str) -> str:
        """Load prompt template from file."""
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / prompt_file
        if not prompt_path.exists():
            # Fallback to v1 if specified version doesn't exist
            if prompt_file != "rag_qa.txt":
                logger.warning(f"Prompt {prompt_file} not found, falling back to rag_qa.txt")
                prompt_path = Path(__file__).parent.parent.parent / "prompts" / "rag_qa.txt"

        if not prompt_path.exists():
            raise RAGError(f"Prompt file not found: {prompt_path}")

        return prompt_path.read_text(encoding="utf-8")


# Test script
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test with different configurations
    print("\n" + "="*70)
    print("TESTING IMPROVED RAG SERVICE")
    print("="*70)

    configs = [
        ("Original (no rerank, v1 prompt)", False, ""),
        ("Improved prompt (v2)", False, "v2"),
        ("With re-ranking (v2)", True, "v2"),
    ]

    question = "Was ist dynamic programming?"

    for name, rerank, prompt_ver in configs:
        print(f"\n{'='*70}")
        print(f"Config: {name}")
        print(f"{'='*70}")

        rag = RAGServiceImproved(
            use_reranking=rerank,
            prompt_version=prompt_ver or "v2"
        )

        try:
            result = rag.answer_question(question, scope="global", verbose=True)

            print(f"\nAnswer: {result['answer']}")
            print(f"\nSources: {len(result['sources'])}")

            if 'diagnostics' in result:
                print(f"Diagnostics: {result['diagnostics']}")

        except Exception as e:
            print(f"Error: {e}")

        input("\nPress ENTER to test next config...")
