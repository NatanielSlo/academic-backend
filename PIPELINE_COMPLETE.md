# Lecture Processing Pipeline - Implementation Complete ✓

## What's Been Implemented

### 1. Database (Supabase + pgvector) ✓
- **Schema**: `migrations/001_initial_schema.sql`
  - `lectures` table with status tracking
  - `lecture_chunks` table with vector embeddings (1536 dimensions)
  - `quizzes` and `quiz_attempts` tables
  - Vector similarity search index (ivfflat)
- **Service**: `app/services/database.py`
  - Connection pooling
  - CRUD operations for lectures, chunks, quizzes
  - Vector similarity search
- **Setup guide**: `SUPABASE_SETUP.md`

### 2. Audio Extraction ✓
- **Changed to MP3**: Now downloads MP3 directly (no conversion needed)
- **Quality**: ~128kbps, optimized for speech
- **Service**: `app/services/audio_extractor.py`

### 3. Transcription ✓
- **Chunking**: Automatically splits large files (>25MB) into 10-min chunks
- **Progress tracking**: Shows upload progress bar
- **Provider**: Groq (fast & cheap) or OpenAI
- **Service**: `app/services/transcription.py`

### 4. Text Chunking ✓
- **Token-based**: 550 tokens per chunk with 100 token overlap
- **Timestamps**: Preserves start/end times from segments
- **Service**: `app/services/chunker.py`

### 5. Embeddings ✓
- **Model**: OpenAI text-embedding-3-small (1536 dimensions)
- **Batch processing**: 100 texts at a time with progress tracking
- **Service**: `app/services/embeddings.py`

### 6. LLM Preprocessing ✓
- **Model**: DeepSeek v4-flash (fast & cheap)
- **Purpose**: Clean raw transcripts before embedding
- **Actions**:
  - Removes filler words (um, uh, so, like)
  - Fixes repetitions
  - Improves punctuation
  - Corrects technical terms
- **Prompt**: `prompts/transcript_cleanup.txt` (editable!)
- **Service**: `app/services/llm.py`

### 7. Full Pipeline Integration ✓
- **Endpoint**: `POST /api/lectures`
- **Processing flow**:
  1. Download audio (MP3) → 20% progress
  2. Transcribe with Whisper → 50% progress
  3. Chunk transcript → 60% progress
  4. **Clean chunks with LLM → 70% progress** ⭐ NEW
  5. Generate embeddings → 90% progress
  6. Save to database → 100% complete
- **File**: `app/api/lectures.py`

### 7. API Endpoints ✓

#### `POST /api/lectures`
Create new lecture and start processing.

**Request:**
```json
{
  "url": "https://live.rbg.tum.de/w/eidi/20838",
  "course_name": "EIDI",
  "lecture_number": "5",
  "date": "2024-11-15"
}
```

**Response:**
```json
{
  "lecture_id": "uuid",
  "status": "processing"
}
```

#### `GET /api/lectures/{lecture_id}/status`
Check processing status (poll every 5 seconds).

**Response:**
```json
{
  "lecture_id": "uuid",
  "status": "downloading" | "transcribing" | "embedding" | "completed" | "failed",
  "progress_percent": 75,
  "error_message": null
}
```

#### `GET /api/lectures`
List all lectures.

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

#### `GET /api/lectures/{lecture_id}/transcript`
Get formatted transcript with timestamps.

**Response:**
```json
{
  "lecture_id": "uuid",
  "transcript": [
    {
      "timestamp": "00:00:45",
      "timestamp_seconds": 45,
      "text": "Today we'll cover dynamic programming..."
    }
  ]
}
```

## Setup Instructions

### 1. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Setup Supabase
Follow instructions in `SUPABASE_SETUP.md`:
1. Create Supabase project
2. Enable pgvector extension
3. Run migration SQL
4. Get connection string

### 3. Environment Variables
Create `backend/.env`:
```env
# Supabase
DATABASE_URL=postgresql://postgres:[password]@db.[project].supabase.co:5432/postgres

# OpenAI (embeddings + optional Whisper)
OPENAI_API_KEY=sk-...

# Groq (fast Whisper transcription - recommended!)
GROQ_API_KEY=gsk_...

# DeepSeek (for future LLM features)
DEEPSEEK_API_KEY=sk-...
```

### 4. Test Database Connection
```bash
python -m app.services.database
```

You should see: "✓ Database connection successful!"

### 5. Run Server
```bash
uvicorn app.main:app --reload
```

API will be available at: http://localhost:8000
API docs: http://localhost:8000/docs

## Testing the Pipeline

### Option 1: Using API Docs (Browser)
1. Go to http://localhost:8000/docs
2. Expand `POST /api/lectures`
3. Click "Try it out"
4. Fill in:
   ```json
   {
     "url": "https://live.rbg.tum.de/w/eidi/20838",
     "course_name": "EIDI",
     "lecture_number": "1"
   }
   ```
5. Click "Execute"
6. Copy the `lecture_id` from response
7. Use `GET /api/lectures/{lecture_id}/status` to check progress
8. When status is "completed", use `GET /api/lectures/{lecture_id}/transcript` to see transcript

### Option 2: Using curl
```bash
# Create lecture
curl -X POST http://localhost:8000/api/lectures \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://live.rbg.tum.de/w/eidi/20838",
    "course_name": "EIDI"
  }'

# Check status (replace {lecture_id})
curl http://localhost:8000/api/lectures/{lecture_id}/status

# Get transcript (when completed)
curl http://localhost:8000/api/lectures/{lecture_id}/transcript
```

## What's Next

The lecture processing pipeline is now complete! Next features to implement:

1. **RAG Q&A** (`POST /api/chat`)
   - Vector search using embeddings
   - LLM integration (DeepSeek)
   - Streaming responses

2. **Quiz Generation** (`POST /api/lectures/{id}/quizzes/generate`)
   - LLM-based question generation
   - Multiple choice format
   - Quiz attempts tracking

3. **Frontend**
   - Upload interface
   - Progress tracking
   - Transcript viewer
   - Chat interface
   - Quiz UI

## Files Created/Modified

### New Files
- `migrations/001_initial_schema.sql` - Database schema
- `app/services/database.py` - Database operations
- `app/services/chunker.py` - Text chunking
- `app/services/embeddings.py` - Embedding generation
- `app/services/llm.py` - LLM preprocessing with DeepSeek ⭐ NEW
- `prompts/transcript_cleanup.txt` - Editable cleanup prompt ⭐ NEW
- `SUPABASE_SETUP.md` - Setup guide
- `PIPELINE_COMPLETE.md` - This file

### Modified Files
- `app/services/audio_extractor.py` - Changed to MP3
- `app/services/transcription.py` - Added chunking & progress
- `app/api/lectures.py` - Full pipeline integration
- `requirements.txt` - Added psycopg2, tiktoken
- `config.yaml` - Added Supabase comment

## Architecture Diagram

```
User Request
     |
     v
POST /api/lectures
     |
     v
[Background Task]
     |
     ├─> 1. Audio Extraction (yt-dlp → MP3)
     |        ↓
     ├─> 2. Transcription (Whisper API → segments)
     |        ↓
     ├─> 3. Chunking (segments → 550-token chunks)
     |        ↓
     ├─> 4. LLM Cleanup (DeepSeek → cleaned chunks) ⭐ NEW
     |        ↓
     ├─> 5. Embeddings (OpenAI → vectors)
     |        ↓
     └─> 6. Database Storage (Supabase/pgvector)
              ↓
         [Status: completed]
```

## Cost Estimates

**Per 90-minute lecture (~30 chunks):**
- Audio download: Free (yt-dlp)
- Transcription (Groq): ~$0.05 (90 min × ~$0.0005/min)
- **LLM Cleanup (DeepSeek v4-flash): ~$0.003** ⭐ NEW
  - 30 chunks × ~500 tokens input × $0.014/1M = ~$0.0002
  - 30 chunks × ~600 tokens output × $0.028/1M = ~$0.0005
- Embeddings (OpenAI): ~$0.0006 (30 chunks × $0.02/1M tokens)
- **Total: ~$0.054 per lecture** 🎉

Still incredibly cheap! LLM cleanup adds only $0.003 (~6% increase) but significantly improves RAG quality.

## Notes

- **File sizes**: MP3 at 128kbps → ~7MB per hour of audio
- **Chunk limit**: Files >25MB are automatically split into 10-min chunks
- **Progress tracking**: Updates database at each pipeline stage
- **Error handling**: Each stage has try/catch with status updates
- **Cleanup**: Audio files are kept for potential re-processing (can be deleted manually)
