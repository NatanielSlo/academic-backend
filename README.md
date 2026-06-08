# AI Academic Assistant - Backend

Backend API for processing TUM lecture recordings and providing AI-powered Q&A.

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install yt-dlp

```bash
pip install yt-dlp
```

Or install system-wide:
- **Windows**: Download from https://github.com/yt-dlp/yt-dlp/releases
- **macOS**: `brew install yt-dlp`
- **Linux**: `sudo apt install yt-dlp` or download binary

### 3. Configure Environment

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env`:
```
DEEPSEEK_API_KEY=your_actual_key
OPENAI_API_KEY=your_actual_key
DATABASE_URL=postgresql://user:password@localhost:5432/academic_assistant
```

### 4. Run the Server

```bash
uvicorn app.main:app --reload
```

API will be available at: http://localhost:8000

## API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Current Features

### ✅ Audio Extraction
- `POST /api/lectures` - Submit lecture URL for processing
- `GET /api/lectures/{lecture_id}/status` - Check processing status
- `GET /api/lectures` - List all lectures

### 🚧 Coming Soon
- Whisper transcription
- Embedding generation
- RAG-based Q&A
- Quiz generation

## Testing

### Test Audio Extraction

```bash
curl -X POST http://localhost:8000/api/lectures \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://live.rbg.tum.de/w/eidi/20838",
    "course_name": "EIDI",
    "lecture_number": "5"
  }'
```

Response:
```json
{
  "lecture_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "processing"
}
```

### Check Status

```bash
curl http://localhost:8000/api/lectures/{lecture_id}/status
```

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Configuration management
│   ├── models/              # Pydantic models
│   │   └── lecture.py
│   ├── services/            # Business logic
│   │   └── audio_extractor.py
│   └── api/                 # API routes
│       └── lectures.py
├── downloads/               # Audio files (gitignored)
├── config.yaml              # App configuration
├── requirements.txt         # Dependencies
└── .env                     # Environment variables (gitignored)
```
