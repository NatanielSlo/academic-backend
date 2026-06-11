# Content Generation System

## Overview

Three-pass pipeline for generating comprehensive study materials from lecture transcripts:

1. **Pass 1:** Extract structured outline (topics, concepts, definitions)
2. **Pass 2a:** Generate detailed Markdown notes
3. **Pass 2b:** Generate comprehensive quiz (multiple question types)
4. **Pass 3:** Verify coverage and identify gaps

## Architecture

```
Lecture Transcript (103k tokens)
         ↓
    Pass 1: Outline Extraction
    - Model: deepseek-v4-pro
    - Output: Structured JSON outline
    - All topics, concepts, timestamps
         ↓
    ┌────────────────┬────────────────┐
    ↓                ↓                ↓
Pass 2a: Notes   Pass 2b: Quiz   Pass 3: Verify
- Markdown       - 20+ questions  - Coverage %
- Detailed       - Mixed types    - Gap report
- Examples       - All topics     - Quality score
```

## API Endpoints

### 1. Generate All Materials
```http
POST /api/content/lectures/{lecture_id}/generate
Content-Type: application/json

{
  "num_quiz_questions": 20
}
```

**Response:**
```json
{
  "lecture_id": "uuid",
  "status": "not_started",
  "progress_percent": 0,
  "current_step": "Queued for processing"
}
```

Starts background generation. Poll status endpoint for progress.

### 2. Check Generation Status
```http
GET /api/content/lectures/{lecture_id}/generation-status
```

**Response:**
```json
{
  "lecture_id": "uuid",
  "status": "generating_notes",
  "progress_percent": 50,
  "current_step": "Saving detailed notes",
  "error_message": null
}
```

**Status values:**
- `not_started` → `generating_outline` → `generating_notes` → `generating_quiz` → `verifying` → `completed`
- Or `failed` if error occurs

### 3. Get Outline
```http
GET /api/content/lectures/{lecture_id}/outline
```

**Response:**
```json
{
  "lecture_id": "uuid",
  "outline": {
    "lecture_metadata": {...},
    "topics": [
      {
        "title": "Introduction to Programming",
        "concepts": [
          {
            "name": "Variables",
            "type": "definition",
            "description": "...",
            "source_quote": "...",
            "timestamp": "00:05:23"
          }
        ]
      }
    ]
  },
  "generated_at": "2024-01-15T10:30:00Z"
}
```

### 4. Get Notes
```http
GET /api/content/lectures/{lecture_id}/notes
```

**Response:**
```json
{
  "lecture_id": "uuid",
  "notes_markdown": "# Lecture Title\n\n## Topic 1\n...",
  "generated_at": "2024-01-15T10:35:00Z"
}
```

### 5. Get Quiz
```http
GET /api/content/lectures/{lecture_id}/comprehensive-quiz
```

**Response:**
```json
{
  "lecture_id": "uuid",
  "quiz_metadata": {
    "total_questions": 20,
    "topics_covered": ["topic1", "topic2"],
    "difficulty_distribution": {
      "basic": 6,
      "intermediate": 10,
      "advanced": 4
    }
  },
  "questions": [
    {
      "question_id": 1,
      "type": "multiple_choice",
      "difficulty": "intermediate",
      "topic": "Dynamic Programming",
      "question_text": "What is memoization?",
      "options": [
        {"label": "A", "text": "..."},
        {"label": "B", "text": "..."}
      ],
      "correct_answer": "B",
      "explanation": "Detailed explanation..."
    }
  ],
  "generated_at": "2024-01-15T10:40:00Z"
}
```

### 6. Get Coverage Report
```http
GET /api/content/lectures/{lecture_id}/coverage-report
```

**Response:**
```json
{
  "lecture_id": "uuid",
  "coverage_summary": {
    "outline_topics": 12,
    "outline_concepts": 45,
    "notes_topics_covered": 12,
    "quiz_topics_covered": 11,
    "coverage_percent": 95.5
  },
  "gaps": [
    {
      "type": "missing_concept",
      "severity": "low",
      "item": "Concept X",
      "recommendation": "Add explanation to notes"
    }
  ],
  "overall_assessment": {
    "coverage_percent": 95.5,
    "quality_score": "excellent",
    "ready_for_student_use": true
  },
  "generated_at": "2024-01-15T10:45:00Z"
}
```

### 7. Get All Materials
```http
GET /api/content/lectures/{lecture_id}/all-materials
```

Returns outline, notes, quiz, and coverage report in one response. Use after generation completes.

## Database Schema

### New Tables

```sql
-- Outlines from Pass 1
CREATE TABLE lecture_outlines (
    id UUID PRIMARY KEY,
    lecture_id UUID REFERENCES lectures(id),
    outline JSONB NOT NULL,
    generated_at TIMESTAMP,
    UNIQUE(lecture_id)
);

-- Notes from Pass 2a
CREATE TABLE lecture_notes (
    id UUID PRIMARY KEY,
    lecture_id UUID REFERENCES lectures(id),
    notes_markdown TEXT NOT NULL,
    generated_at TIMESTAMP,
    UNIQUE(lecture_id)
);

-- Quizzes from Pass 2b
CREATE TABLE comprehensive_quizzes (
    id UUID PRIMARY KEY,
    lecture_id UUID REFERENCES lectures(id),
    quiz_data JSONB NOT NULL,
    num_questions INTEGER,
    generated_at TIMESTAMP,
    UNIQUE(lecture_id)
);

-- Coverage reports from Pass 3
CREATE TABLE coverage_reports (
    id UUID PRIMARY KEY,
    lecture_id UUID REFERENCES lectures(id),
    report JSONB NOT NULL,
    coverage_percent NUMERIC(5,2),
    quality_score TEXT,
    generated_at TIMESTAMP,
    UNIQUE(lecture_id)
);

-- Status tracking
CREATE TABLE content_generation_status (
    id UUID PRIMARY KEY,
    lecture_id UUID REFERENCES lectures(id),
    status TEXT NOT NULL,
    progress_percent INTEGER,
    current_step TEXT,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(lecture_id)
);
```

## Testing

### Test Script

```bash
cd backend
python test_content_generation.py
```

This will:
1. Load `transcript_output.json`
2. Run Pass 1 (outline extraction)
3. Optionally run Pass 2a (notes)
4. Run Pass 2b (quiz)
5. Run Pass 3 (coverage verification)
6. Save all outputs to `logs/content_generation/`

### Manual API Testing

```bash
# Start server
uvicorn app.main:app --reload

# In another terminal:
# 1. Start generation
curl -X POST http://localhost:8000/api/content/lectures/{id}/generate \
  -H "Content-Type: application/json" \
  -d '{"num_quiz_questions": 10}'

# 2. Check status (poll every 5 seconds)
curl http://localhost:8000/api/content/lectures/{id}/generation-status

# 3. Get results after completion
curl http://localhost:8000/api/content/lectures/{id}/outline
curl http://localhost:8000/api/content/lectures/{id}/notes
curl http://localhost:8000/api/content/lectures/{id}/comprehensive-quiz
curl http://localhost:8000/api/content/lectures/{id}/coverage-report
```

## Prompt Engineering

Prompts are stored in `backend/prompts/`:

- `outline_extraction.txt` - Pass 1 prompt
- `notes_generation.txt` - Pass 2a prompt
- `quiz_generation.txt` - Pass 2b prompt
- `coverage_verification.txt` - Pass 3 prompt

To improve quality, edit these prompts. They include:
- Clear requirements
- Output format specifications
- Quality criteria
- Examples

## Cost Estimates

**Per lecture (~110 minutes, 103k input tokens):**

| Pass | Model | Input | Output | Cost |
|------|-------|-------|--------|------|
| 1: Outline | v4-pro | 103k | 8k | ~$0.15 |
| 2a: Notes | v4-pro | 20k | 16k | ~$0.08 |
| 2b: Quiz | v4-pro | 20k | 8k | ~$0.06 |
| 3: Verify | v4-flash | 40k | 4k | ~$0.01 |
| **Total** | | | | **~$0.30** |

(Based on DeepSeek v4 pricing: pro ~$0.14/1M input, flash ~$0.02/1M)

## Performance

**Expected timing:**
- Pass 1: 30-60s (full transcript analysis)
- Pass 2a: 20-40s (notes generation)
- Pass 2b: 20-40s (quiz generation)
- Pass 3: 10-20s (verification)
- **Total: ~2-3 minutes per lecture**

## Quality Guarantees

The three-pass system ensures:

✅ **Zero-loss coverage** - outline includes ALL content
✅ **Verification** - Pass 3 checks coverage & quality
✅ **Traceability** - timestamps & quotes for each concept
✅ **Consistency** - all materials derived from same outline
✅ **Quality score** - automatic assessment (excellent/good/fair/poor)

## Future Enhancements

Potential improvements:

1. **Incremental updates** - regenerate only changed sections
2. **Custom prompts** - per-course prompt templates
3. **Multi-language** - detect language, use appropriate prompts
4. **Interactive refinement** - allow manual gap filling
5. **Flashcard generation** - Pass 4 for spaced repetition
6. **Difficulty calibration** - adjust based on student performance

## Troubleshooting

**Generation fails:**
- Check `content_generation_status` table for error message
- Review logs in `logs/content_generation/`
- Verify lecture has completed processing
- Check DeepSeek API key is valid

**Low coverage score:**
- Review gaps in coverage report
- Check if transcript quality is poor
- Consider adjusting prompts for better extraction

**Invalid JSON output:**
- LLM sometimes wraps JSON in markdown code blocks
- Parser handles this automatically
- If still failing, check prompt clarity

**Slow generation:**
- DeepSeek v4-pro can be slower for complex analysis
- Consider using v4-flash for simpler lectures
- Parallel Pass 2a+2b is possible (future enhancement)
