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


class RAGService:
    """Service for Retrieval-Augmented Generation Q&A."""

    def __init__(self):
        self.db = DatabaseService()
        self.embedding_service = EmbeddingService()
        self.llm_service = LLMService()
        self.top_k = config.rag.top_k
        self.similarity_threshold = config.rag.similarity_threshold
        self.use_reranking = config.rag.use_reranking
        self.prompt_version = config.rag.prompt_version
        self.preprocess_query = config.rag.preprocess_query

        logger.info(
            f"Initialized RAG service (top_k={self.top_k}, threshold={self.similarity_threshold}, "
            f"reranking={self.use_reranking}, prompt={self.prompt_version}, preprocess={self.preprocess_query})"
        )

    def answer_question(
        self,
        question: str,
        scope: str = "global",
        scope_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Answer a question using RAG.

        Args:
            question: User's question
            scope: "global", "course", or "lecture"
            scope_id: Course name (if scope=course) or lecture UUID (if scope=lecture)

        Returns:
            Dict with:
                - answer: LLM-generated answer
                - sources: List of source chunks used
                - question: Original question
                - scope: Search scope used

        Raises:
            RAGError: If RAG pipeline fails
        """
        try:
            logger.info(f"Answering question (scope={scope}, scope_id={scope_id}): {question[:100]}...")

            # Step 0: Preprocess query (translate + optimize for RAG)
            if self.preprocess_query:
                optimized_question = self._preprocess_query(question)
                logger.info(f"Preprocessed query: {question[:50]}... → {optimized_question[:50]}...")
            else:
                optimized_question = question

            # Step 1: Embed the (optimized) question
            
            question_embedding = self._embed_question(optimized_question)

            # Step 2: Retrieve relevant chunks (get more initially if reranking)
            initial_k = self.top_k * 3 if self.use_reranking else self.top_k
            chunks = self._retrieve_chunks(
                question_embedding,
                scope=scope,
                scope_id=scope_id,
                top_k=initial_k
            )

            # Log retrieved chunks for debugging
            if chunks:
                similarities = [c.get('similarity', 0) for c in chunks]
                logger.info(f"Retrieved {len(chunks)} chunks, similarities: {[f'{s:.3f}' for s in similarities[:5]]}")

            # Step 2.5: Optional re-ranking (if enabled in config)
            if self.use_reranking and chunks:
                logger.info(f"Re-ranking {len(chunks)} chunks...")
                chunks = self._rerank_chunks(question, chunks)
                logger.info(f"After re-ranking: {len(chunks)} chunks kept")

            if not chunks:
                logger.warning("No relevant chunks found for question")
                return {
                    "answer": "Ich konnte keine relevanten Informationen in den Vorlesungen finden, um diese Frage zu beantworten.",
                    "sources": [],
                    "question": question,
                    "scope": scope
                }

            # Step 3: Generate answer using LLM
            # Use ORIGINAL question for answer (user asked the original)
            answer = self._generate_answer(question, chunks)

            # Step 4: Format sources
            sources = self._format_sources(chunks)

            logger.info(f"Generated answer with {len(sources)} sources")

            result = {
                "answer": answer,
                "sources": sources,
                "question": question,
                "scope": scope
            }

            # Include optimized query for debugging (if preprocessing was used)
            if self.preprocess_query and optimized_question != question:
                result["optimized_query"] = optimized_question

            return result

        except (EmbeddingError, DatabaseError, LLMError) as e:
            error_msg = f"RAG pipeline failed: {str(e)}"
            logger.error(error_msg)
            raise RAGError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error in RAG: {str(e)}"
            logger.error(error_msg)
            raise RAGError(error_msg)

    def _preprocess_query(self, question: str) -> str:
        """
        Preprocess user query using LLM to optimize for RAG.

        - Translates to German if needed
        - Expands with synonyms
        - Makes more explicit/specific
        - Adds relevant academic context

        Args:
            question: Original user question

        Returns:
            Optimized question for better vector search
        """
        try:
            # Load preprocessing prompt
            prompt_template = self._load_prompt("query_preprocessing.txt")

            # Combine with user question
            full_prompt = f"{prompt_template}\n\nBenutzeranfrage: {question}\n\nOptimierte Anfrage:"

            # Call LLM (use fast model, low temperature)
            optimized = self.llm_service.complete(
                prompt=full_prompt,
                model="simple",
                temperature=0.2,  # Low temp for consistent translation/expansion
                max_tokens=2000
            ).strip()


            # Fallback to original if LLM returns empty or too long
            if not optimized or len(optimized) > 500:
                logger.warning(f"Query preprocessing failed or too long, using original")
                return question

            logger.debug(f"Query preprocessed: '{question}' → '{optimized}'")
            return optimized

        except Exception as e:
            logger.warning(f"Query preprocessing failed: {e}, using original query")
            return question

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
        scope_id: Optional[str],
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant chunks using vector similarity search.

        Args:
            query_embedding: Query vector
            scope: Search scope
            scope_id: Scope identifier
            top_k: Number of chunks to retrieve (default: self.top_k)

        Returns:
            List of chunk dicts with metadata
        """
        if top_k is None:
            top_k = self.top_k

        logger.debug(f"Searching for chunks (scope={scope}, top_k={top_k})...")

        # Map scope to database parameters
        lecture_id = scope_id if scope == "lecture" else None
        course_name = scope_id if scope == "course" else None

        # Search database
        chunks = self.db.search_similar_chunks(
            query_embedding=query_embedding,
            top_k=top_k,
            lecture_id=lecture_id,
            course_name=course_name
        )

        # Filter by similarity threshold
        filtered_chunks = [
            chunk for chunk in chunks
            if chunk.get('similarity', 0) >= self.similarity_threshold
        ]

        logger.debug(f"Retrieved {len(filtered_chunks)} chunks (filtered from {len(chunks)} by threshold={self.similarity_threshold})")

        if len(filtered_chunks) == 0 and len(chunks) > 0:
            best_similarity = max(c.get('similarity', 0) for c in chunks)
            logger.warning(
                f"All {len(chunks)} chunks filtered out by threshold! "
                f"Best similarity was {best_similarity:.3f}. Consider lowering threshold."
            )

        return filtered_chunks

    def _rerank_chunks(
        self,
        question: str,
        chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Re-rank chunks using LLM relevance scoring.

        This is expensive (one LLM call per chunk) so use sparingly.
        For production, consider using a dedicated reranker model.

        Args:
            question: Original question
            chunks: Retrieved chunks

        Returns:
            Top self.top_k chunks sorted by relevance
        """
        if not chunks:
            return []

        scored_chunks = []

        for i, chunk in enumerate(chunks):
            text_preview = chunk.get('text', '')[:400]

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
                score = float(response.split()[0])
                score = max(0, min(10, score))  # Clamp to 0-10

                chunk['relevance_score'] = score
                scored_chunks.append(chunk)

            except Exception as e:
                logger.warning(f"Failed to score chunk {i+1}: {e}, using similarity as fallback")
                chunk['relevance_score'] = chunk.get('similarity', 0) * 10
                scored_chunks.append(chunk)

        # Sort by relevance score and take top N
        scored_chunks.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        return scored_chunks[:self.top_k]

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

        # Load RAG prompt template (with version support)
        prompt_file = f"rag_qa_{self.prompt_version}.txt" if self.prompt_version != "v1" else "rag_qa.txt"
        prompt_template = self._load_prompt(prompt_file)

        # Build context from chunks
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            course = chunk.get('course_name', 'Unknown')
            lecture = chunk.get('lecture_number', 'Unknown')
            timestamp = self._format_timestamp(chunk.get('start_timestamp_seconds', 0))
            text = chunk.get('text', '')

            context_parts.append(
                f"[Quelle {i}] Kurs: {course}, Vorlesung: {lecture}, Zeit: {timestamp}\n{text}"
            )

        context = "\n\n".join(context_parts)

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

            # Include relevance score if re-ranking was used
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

        # Fallback to v1 if specified version doesn't exist
        if not prompt_path.exists():
            if prompt_file != "rag_qa.txt":
                logger.warning(f"Prompt {prompt_file} not found, falling back to rag_qa.txt")
                prompt_path = Path(__file__).parent.parent.parent / "prompts" / "rag_qa.txt"

            if not prompt_path.exists():
                raise RAGError(f"Prompt file not found: {prompt_path}")

        return prompt_path.read_text(encoding="utf-8")


# Test script
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    rag = RAGService()

    # Test question
    question = "Was ist dynamic programming?"

    print(f"Question: {question}\n")

    result = rag.answer_question(question, scope="global")

    print("="*70)
    print("ANSWER:")
    print("="*70)
    print(result['answer'])
    print()

    print("="*70)
    print(f"SOURCES ({len(result['sources'])}):")
    print("="*70)
    for i, source in enumerate(result['sources'], 1):
        print(f"{i}. {source['course_name']} L{source['lecture_number']} [{source['timestamp']}]")
        print(f"   Similarity: {source['similarity']}")
        print(f"   {source['chunk_text']}")
        print()
