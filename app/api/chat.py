from fastapi import APIRouter, HTTPException
import logging

from app.models.chat import ChatRequest, ChatResponse, ChatSource
from app.services.rag import RAGService, RAGError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Initialize RAG service
rag_service = RAGService()


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Answer a question using RAG (Retrieval-Augmented Generation).

    The system will:
    1. Embed the user's question
    2. Search for relevant lecture chunks using vector similarity
    3. Filter by scope (global/course/lecture)
    4. Generate an answer using LLM with retrieved context
    5. Return answer with source citations

    **Scopes:**
    - `global`: Search across all lectures
    - `course`: Search within a specific course (requires scope_id = course name)
    - `lecture`: Search within a specific lecture (requires scope_id = lecture UUID)

    **Example requests:**

    Global search:
    ```json
    {
      "question": "Was ist dynamic programming?",
      "scope": "global"
    }
    ```

    Course-specific search:
    ```json
    {
      "question": "Wie funktioniert Rekursion?",
      "scope": "course",
      "scope_id": "EIDI"
    }
    ```

    Lecture-specific search:
    ```json
    {
      "question": "Was wurde über Fibonacci gesagt?",
      "scope": "lecture",
      "scope_id": "123e4567-e89b-12d3-a456-426614174000"
    }
    ```
    """
    # Validate scope_id requirements
    if request.scope in ["course", "lecture"] and not request.scope_id:
        raise HTTPException(
            status_code=400,
            detail=f"scope_id is required when scope is '{request.scope}'"
        )

    try:
        logger.info(f"Chat request: {request.question[:50]}... (scope={request.scope})")

        # Generate answer using RAG
        result = rag_service.answer_question(
            question=request.question,
            scope=request.scope,
            scope_id=request.scope_id
        )

        # Convert to response model
        response = ChatResponse(
            answer=result["answer"],
            sources=[ChatSource(**source) for source in result["sources"]],
            question=result["question"],
            scope=result["scope"]
        )

        logger.info(f"Chat response generated with {len(response.sources)} sources")

        return response

    except RAGError as e:
        logger.error(f"RAG error: {e}")
        raise HTTPException(status_code=500, detail=f"RAG error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
