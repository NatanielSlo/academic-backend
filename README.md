# AI Academic Assistant - Backend

FastAPI backend for processing lecture recordings and generating comprehensive study materials.

## Features

### 🎥 Lecture Processing
- Extract audio from lecture URLs (yt-dlp)
- Transcribe with OpenAI Whisper
- Chunk and embed for RAG search
- Store in PostgreSQL with pgvector

### 💬 RAG Q&A
- Ask questions about lectures
- Vector similarity search
- Context-aware responses via DeepSeek
- Source citations with timestamps

### 📚 **Content Generation (NEW!)**
- **Structured Outline**: Extract all topics, concepts, definitions
- **Detailed Notes**: Comprehensive Markdown study notes
- **Comprehensive Quiz**: 20+ questions, mixed types, all difficulty levels
- **Coverage Verification**: Automatic quality check & gap detection

## Tech Stack

- **Framework**: FastAPI
- **Database**: PostgreSQL + pgvector
- **LLM**: DeepSeek API (v4-flash, v4-pro)
- **Transcription**: OpenAI Whisper API
- **Embeddings**: OpenAI text-embedding-3-small

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure
Copy `.env.example` to `.env` and set:
```
DEEPSEEK_API_KEY=your_key
OPENAI_API_KEY=your_key
DATABASE_URL=postgresql://...
```

### 3. Run Migrations
```bash
python run_migration.py
```

### 4. Start Server
```bash
uvicorn app.main:app --reload
```

API available at `http://localhost:8000`

### 5. Test Content Generation
```bash
python test_content_generation.py
```

## Documentation

📖 **Start here:**
- **[QUICKSTART.md](QUICKSTART.md)** - Get running in 5 minutes
- **[BACKEND_SPEC.md](BACKEND_SPEC.md)** - Complete system specification

📚 **Content Generation:**
- **[CONTENT_GENERATION.md](CONTENT_GENERATION.md)** - Technical documentation
- **[USAGE_EXAMPLE.md](USAGE_EXAMPLE.md)** - Code examples & workflows
- **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** - What was built
- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - Pre-launch checks

## API Overview

### Lecture Processing
```http
POST   /api/lectures              # Submit lecture URL
GET    /api/lectures              # List all lectures
GET    /api/lectures/{id}/status  # Check processing status
GET    /api/lectures/{id}/transcript  # Get transcript
```

### Q&A
```http
POST   /api/chat                  # Ask questions (RAG)
```

### Content Generation
```http
POST   /api/content/lectures/{id}/generate           # Start generation
GET    /api/content/lectures/{id}/generation-status  # Poll progress
GET    /api/content/lectures/{id}/outline            # Get outline
GET    /api/content/lectures/{id}/notes              # Get notes
GET    /api/content/lectures/{id}/comprehensive-quiz # Get quiz
GET    /api/content/lectures/{id}/coverage-report    # Get quality report
GET    /api/content/lectures/{id}/all-materials      # Get everything
```

Full API docs: `http://localhost:8000/docs` (auto-generated)

## Project Structure

```
backend/
├── app/
│   ├── api/              # API endpoints
│   │   ├── lectures.py   # Lecture processing
│   │   ├── chat.py       # RAG Q&A
│   │   └── content.py    # Content generation (NEW)
│   ├── models/           # Pydantic models
│   │   ├── lecture.py
│   │   ├── chat.py
│   │   └── content.py    # (NEW)
│   ├── services/         # Business logic
│   │   ├── llm.py        # LLM client
│   │   ├── rag.py        # RAG search
│   │   ├── content_generator.py  # (NEW)
│   │   └── ...
│   ├── config.py         # Configuration
│   └── main.py           # FastAPI app
├── prompts/              # LLM prompts (NEW)
│   ├── outline_extraction.txt
│   ├── notes_generation.txt
│   ├── quiz_generation.txt
│   └── coverage_verification.txt
├── migrations/           # Database migrations
├── logs/                 # Generated files
└── tests/                # Test scripts
```

## Content Generation Pipeline

```
                    Lecture Transcript
                            ↓
              ┌─────────────────────────┐
              │   PASS 1: Outline       │
              │   Extract structure     │
              └─────────────────────────┘
                            ↓
              ┌──────────────┬──────────────┐
              ↓              ↓              ↓
         ┌────────┐    ┌────────┐    ┌────────┐
         │ Notes  │    │  Quiz  │    │ Verify │
         │ Pass2a │    │ Pass2b │    │ Pass3  │
         └────────┘    └────────┘    └────────┘
              │              │              │
              └──────────────┴──────────────┘
                            ↓
                  Complete Study Materials
```

**Output:**
- Structured JSON outline
- Markdown notes (10-20 pages)
- 20+ quiz questions
- Coverage report (95%+ quality)

**Cost:** ~$0.30 per 110-minute lecture

**Time:** 2-3 minutes

## Database Schema

### Core Tables
- `lectures` - Lecture metadata
- `lecture_chunks` - Embedded text chunks for RAG

### Content Generation Tables (NEW)
- `lecture_outlines` - Structured outlines
- `lecture_notes` - Markdown notes
- `comprehensive_quizzes` - Quiz questions
- `coverage_reports` - Quality reports
- `content_generation_status` - Async tracking

## Development

### Run Tests
```bash
# Test content generation
python test_content_generation.py

# Test RAG search
python app/tests/test_rag.py

# Check database
python app/tests/check_database.py
```

### Add Migrations
1. Create `migrations/XXX_description.sql`
2. Run `python run_migration.py`

### Adjust Prompts
Edit files in `prompts/` and regenerate to see improvements.

### View Logs
```bash
# LLM interactions
ls logs/llm/

# Content generation
ls logs/content_generation/
```

## Cost Estimates

**Per 110-minute lecture:**
- Audio extraction: Free (yt-dlp)
- Transcription: ~$0.54 (Whisper)
- Embedding: ~$0.001 (negligible)
- Content generation: ~$0.30 (DeepSeek)
- **Total: ~$0.84 per lecture**

**Q&A:** ~$0.0001 per question (DeepSeek v4-flash)

## Deployment

### Local Development
See above (Quick Start)

### Production (Render)
1. Create PostgreSQL addon
2. Set environment variables
3. Deploy service
4. Run migrations: `python run_migration.py`
5. Check: `GET /health`

Full checklist: **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)**

## Troubleshooting

**Common issues:**

1. **"No transcript found"**
   - Lecture not processed yet
   - Process via `/api/lectures` first

2. **"DeepSeek API error: 401"**
   - Check `DEEPSEEK_API_KEY` in `.env`

3. **"Migration already run"**
   - Tables already exist, skip migration

4. **"Generation failed"**
   - Check logs: `logs/content_generation/`
   - Review error in `content_generation_status` table

See individual docs for detailed troubleshooting.

## Contributing

1. Follow existing code structure
2. Add tests for new features
3. Update documentation
4. Run migration for schema changes
5. Test end-to-end before committing

## Support

- API Docs: `http://localhost:8000/docs`
- Documentation: See `.md` files in this directory

---

**Ready to process lectures and generate study materials!** 🚀
