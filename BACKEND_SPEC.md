# Backend Specification: AI Academic Assistant

## Project Overview
A personal academic assistant tool for TUM (Technical University of Munich) students that processes lecture recordings, provides AI-powered Q&A, and generates practice quizzes. Single-user MVP with focus on cost-effectiveness and ease of use.

## Tech Stack
- **Framework:** Python FastAPI
- **Database:** PostgreSQL with pgvector extension
- **Vector Search:** pgvector (PostgreSQL extension for embeddings)
- **Audio Extraction:** yt-dlp (audio-only to save bandwidth)
- **Transcription:** OpenAI Whisper API
- **Embeddings:** OpenAI text-embedding-3-small ($0.02/1M tokens)
- **LLM:** DeepSeek API
  - `deepseek-v4-flash` for simple tasks (Q&A, retrieval)
  - `deepseek-v4-pro` for complex tasks (quiz generation)
- **Background Jobs:** FastAPI BackgroundTasks (simple async processing)

## Hosting & Deployment
- **Development:** Local
- **Production:** Render free tier (includes PostgreSQL, auto-sleep after 15min inactivity)
- **Frontend:** Vercel (separate deployment, communicates via REST API)

## Core Features

### 1. Lecture Processing Pipeline
**Endpoint:** `POST /api/lectures`

**Input:**
```json
{
  "url": "https://live.rbg.tum.de/w/eidi/20838",
  "course_name": "EIDI", // optional
  "lecture_number": "5", // optional
  "date": "2024-11-15" // optional
}
```

**Processing Flow (Background Task):**
1. Extract audio using yt-dlp (audio-only format)
2. Upload audio to OpenAI Whisper API for transcription (returns text + word-level timestamps)
3. Chunk transcript into 500-600 token segments with 100 token overlap
4. Generate embeddings using `text-embedding-3-small`
5. Store in PostgreSQL:
   - Lecture metadata (id, url, course_name, lecture_number, date, status)
   - Full transcript with timestamps
   - Chunked segments with embeddings in pgvector
6. Update processing status throughout

**Response:**
```json
{
  "lecture_id": "uuid",
  "status": "processing"
}
```

### 2. Processing Status
**Endpoint:** `GET /api/lectures/{lecture_id}/status`

**Response:**
```json
{
  "lecture_id": "uuid",
  "status": "downloading" | "transcribing" | "embedding" | "completed" | "failed",
  "progress_percent": 45,
  "error_message": null
}
```

Frontend polls this every 5 seconds during processing.

### 3. Lecture List
**Endpoint:** `GET /api/lectures`

**Response:**
```json
{
  "lectures": [
    {
      "id": "uuid",
      "url": "https://...",
      "course_name": "EIDI",
      "lecture_number": "5",
      "date": "2024-11-15",
      "status": "completed",
      "created_at": "2024-11-15T10:30:00Z"
    }
  ]
}
```

### 4. Transcript Retrieval
**Endpoint:** `GET /api/lectures/{lecture_id}/transcript`

**Response:**
```json
{
  "lecture_id": "uuid",
  "transcript": [
    {
      "timestamp": "00:00:45",
      "timestamp_seconds": 45,
      "text": "Today we'll cover dynamic programming..."
    },
    {
      "timestamp": "00:01:30",
      "timestamp_seconds": 90,
      "text": "Let's start with the Fibonacci example..."
    }
  ]
}
```

Timestamps every 30-60 seconds, clickable to jump to video position.

### 5. RAG Question Answering
**Endpoint:** `POST /api/chat`

**Input:**
```json
{
  "question": "What is dynamic programming?",
  "scope": "global" | "course" | "lecture",
  "scope_id": null | "course_name" | "lecture_uuid"
}
```

**Processing:**
1. Embed the question using `text-embedding-3-small`
2. Vector search in pgvector (filter by scope if not global)
3. Retrieve top 5 most relevant chunks
4. Construct prompt with context
5. Call DeepSeek v4-flash with:
   ```
   Context: [retrieved chunks]
   Question: [user question]
   Answer based only on the provided lecture content.
   ```
6. Stream response back

**Response:**
```json
{
  "answer": "Dynamic programming is...",
  "sources": [
    {
      "lecture_id": "uuid",
      "course_name": "EIDI",
      "lecture_number": "5",
      "timestamp": "00:15:30",
      "chunk_text": "excerpt..."
    }
  ]
}
```

### 6. Quiz Generation
**Endpoint:** `POST /api/lectures/{lecture_id}/quizzes/generate`

**Input:**
```json
{
  "num_questions": 10
}
```

**Processing:**
1. Retrieve full transcript for lecture
2. Call DeepSeek v4-pro with prompt:
   ```
   Generate {num_questions} multiple choice questions based on this lecture transcript.
   Each question should have 4 options (A, B, C, D) with exactly one correct answer.
   Focus on key concepts and understanding, not trivial details.
   Return as JSON array.
   ```
3. Parse and validate response
4. Store quiz in database

**Response:**
```json
{
  "quiz_id": "uuid",
  "lecture_id": "uuid",
  "questions": [
    {
      "question_id": "uuid",
      "question_text": "What is the time complexity of...",
      "options": [
        {"label": "A", "text": "O(n)"},
        {"label": "B", "text": "O(n²)"},
        {"label": "C", "text": "O(log n)"},
        {"label": "D", "text": "O(1)"}
      ],
      "correct_answer": "B"
    }
  ],
  "created_at": "2024-11-15T11:00:00Z"
}
```

### 7. Quiz List for Lecture
**Endpoint:** `GET /api/lectures/{lecture_id}/quizzes`

**Response:**
```json
{
  "quizzes": [
    {
      "quiz_id": "uuid",
      "created_at": "2024-11-15T11:00:00Z",
      "num_questions": 10,
      "attempts": 2,
      "best_score": 9
    }
  ]
}
```

### 8. Get Quiz
**Endpoint:** `GET /api/quizzes/{quiz_id}`

**Response:** Same structure as quiz generation response, but WITHOUT `correct_answer` field (that's only revealed after submission).

### 9. Submit Quiz Attempt
**Endpoint:** `POST /api/quizzes/{quiz_id}/attempts`

**Input:**
```json
{
  "answers": {
    "question_uuid_1": "B",
    "question_uuid_2": "A",
    ...
  }
}
```

**Processing:**
1. Load quiz from database
2. Grade answers
3. Store attempt (score, timestamp, user answers)
4. Return results

**Response:**
```json
{
  "attempt_id": "uuid",
  "score": 8,
  "total": 10,
  "questions": [
    {
      "question_id": "uuid",
      "question_text": "What is...",
      "your_answer": "B",
      "correct_answer": "B",
      "is_correct": true,
      "explanation": "excerpt from lecture explaining this concept..."
    }
  ],
  "completed_at": "2024-11-15T11:30:00Z"
}
```

## Database Schema

### lectures
```sql
CREATE TABLE lectures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url TEXT NOT NULL,
    course_name TEXT,
    lecture_number TEXT,
    date DATE,
    status TEXT NOT NULL, -- 'processing', 'completed', 'failed'
    progress_percent INTEGER DEFAULT 0,
    error_message TEXT,
    full_transcript JSONB, -- array of {timestamp, timestamp_seconds, text}
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### lecture_chunks
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE lecture_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lecture_id UUID REFERENCES lectures(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    start_timestamp_seconds INTEGER,
    end_timestamp_seconds INTEGER,
    embedding vector(1536), -- text-embedding-3-small dimension
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ON lecture_chunks USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX ON lecture_chunks(lecture_id);
```

### quizzes
```sql
CREATE TABLE quizzes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lecture_id UUID REFERENCES lectures(id) ON DELETE CASCADE,
    questions JSONB NOT NULL, -- array of question objects
    created_at TIMESTAMP DEFAULT NOW()
);
```

### quiz_attempts
```sql
CREATE TABLE quiz_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quiz_id UUID REFERENCES quizzes(id) ON DELETE CASCADE,
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    answers JSONB NOT NULL, -- {question_id: user_answer}
    completed_at TIMESTAMP DEFAULT NOW()
);
```

## Configuration Management
**File:** `config.yaml`

```yaml
llm:
  provider: "deepseek"  # openai, anthropic, deepseek
  models:
    simple: "deepseek-v4-flash"
    complex: "deepseek-v4-pro"
  api_key: "${DEEPSEEK_API_KEY}"  # from environment variable

openai:
  api_key: "${OPENAI_API_KEY}"
  whisper_model: "whisper-1"
  embedding_model: "text-embedding-3-small"

database:
  url: "${DATABASE_URL}"  # PostgreSQL connection string

chunking:
  chunk_size: 550  # tokens
  overlap: 100     # tokens

rag:
  top_k: 5  # number of chunks to retrieve
  similarity_threshold: 0.7
```

**Environment Variables:**
- `DEEPSEEK_API_KEY`
- `OPENAI_API_KEY`
- `DATABASE_URL` (Render provides this automatically)

## LLM Client Abstraction
Create a simple wrapper for easy model switching:

```python
class LLMClient:
    def __init__(self, config):
        self.config = config
        self.provider = config.llm.provider
        
    def complete(self, prompt: str, complexity: str = "simple") -> str:
        model = self.config.llm.models[complexity]
        
        if self.provider == "deepseek":
            return self._deepseek_complete(prompt, model)
        elif self.provider == "openai":
            return self._openai_complete(prompt, model)
        # ... other providers
    
    def _deepseek_complete(self, prompt: str, model: str) -> str:
        # DeepSeek API call
        pass
```

## Error Handling
- Audio extraction fails → mark lecture as 'failed', store error message
- Transcription fails → retry once, then mark as failed
- Embedding API rate limit → exponential backoff, queue for retry
- Quiz generation returns invalid JSON → retry with stricter prompt, fallback to 5 questions instead of 10

## API Costs (Estimates)
**Per 90-minute lecture:**
- Audio extraction: Free (yt-dlp)
- Transcription (Whisper API): ~$0.54 (90 min × $0.006/min)
- Embedding (~30 chunks): ~$0.0006
- Total per lecture: ~$0.54

**Per interaction:**
- Q&A (DeepSeek v4-flash): ~$0.0001
- Quiz generation (DeepSeek v4-pro): ~$0.003
- Quiz retake: Free (no API call)

## Security Considerations
- Single-user app (no authentication needed for MVP)
- Validate URLs before processing (whitelist `live.rbg.tum.de` domain)
- Sanitize user input for SQL injection (use parameterized queries)
- Rate limit API endpoints (prevent abuse)
- Don't expose API keys in responses

## Testing Strategy
- Unit tests: LLM client, chunking logic, embedding generation
- Integration tests: Full pipeline (mock external APIs)
- Manual testing: Process one real lecture, verify transcript accuracy, test Q&A quality

## Next Steps for Backend Developer
1. Set up FastAPI project structure
2. Configure PostgreSQL with pgvector extension
3. Implement configuration management (config.yaml + env vars)
4. Build lecture processing pipeline (yt-dlp → Whisper → embedding)
5. Implement RAG search with pgvector
6. Create quiz generation endpoint
7. Set up background task processing
8. Deploy to Render with PostgreSQL addon
9. Document API endpoints (auto-generate with FastAPI/OpenAPI)
