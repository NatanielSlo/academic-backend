# Quick Start Guide - Content Generation

Get up and running with comprehensive material generation in 5 minutes.

## Prerequisites

✅ Backend already set up with:
- PostgreSQL database running
- DeepSeek API key configured
- OpenAI API key configured (for Whisper)
- Python environment with dependencies

## Step 1: Run Migration (30 seconds)

```bash
cd backend
python run_migration.py
```

Expected output:
```
INFO - Running migration: 002_add_content_generation.sql
INFO - ✓ Migration 002_add_content_generation.sql completed successfully
INFO - ✓ All 1 migration(s) completed successfully
```

This creates 5 new tables for content generation.

## Step 2: Test with Example Transcript (3 minutes)

```bash
python test_content_generation.py
```

This will:
1. Load `transcript_output.json` (~103k tokens)
2. Ask for confirmation before each pass
3. Generate outline, notes, quiz, and coverage report
4. Save outputs to `logs/content_generation/`

### What to expect:

```
==================================================================
THREE-PASS CONTENT GENERATION PIPELINE
Lecture ID: test-lecture-001
Transcript: 385931 chars (~96k tokens)
==================================================================

[PASS 1] Extracting outline from transcript
Model: deepseek-v4-pro
Transcript length: 385931 chars (~96482 tokens)

Proceed with outline extraction? (y/n): y

[Processing for 30-60 seconds...]

[PASS 1 SUCCESS] Extracted outline in 45.3s
  Topics: 12
  Concepts: 45
  Output size: 15234 chars

[Continue through Pass 2a, 2b, 3...]
```

## Step 3: Check Generated Files

```bash
ls logs/content_generation/
```

You should see:
```
outline_test-lecture-001_YYYYMMDD_HHMMSS.json    # Structured outline
notes_test-lecture-001_YYYYMMDD_HHMMSS.md        # Markdown notes
quiz_test-lecture-001_YYYYMMDD_HHMMSS.json       # Quiz questions
coverage_test-lecture-001_YYYYMMDD_HHMMSS.json   # Coverage report
```

**Review the outputs:**
```bash
# View notes
cat logs/content_generation/notes_*.md | less

# Check quiz questions
cat logs/content_generation/quiz_*.json | jq '.questions[0]'

# See coverage score
cat logs/content_generation/coverage_*.json | jq '.overall_assessment'
```

## Step 4: Start API Server

```bash
uvicorn app.main:app --reload
```

Server runs on `http://localhost:8000`

## Step 5: Test API (2 minutes)

### 5a. Get a lecture ID

First, you need a processed lecture. Either:

**Option A: Use existing lecture**
```bash
curl http://localhost:8000/api/lectures | jq '.lectures[0].id'
```

**Option B: Process new lecture**
```bash
curl -X POST http://localhost:8000/api/lectures \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://live.rbg.tum.de/w/eidi/20838",
    "course_name": "EIDI"
  }' | jq -r '.lecture_id'
```

Save the lecture ID as a variable:
```bash
LECTURE_ID="550e8400-e29b-41d4-a716-446655440000"  # replace with actual ID
```

### 5b. Start generation

Notes and quiz are generated via separate endpoints. Each will generate the
shared outline first if it doesn't already exist. They share a single status
row, so run one at a time.

```bash
# Generate detailed notes (no body required)
curl -X POST "http://localhost:8000/api/content/lectures/$LECTURE_ID/generate-notes"

# Generate the comprehensive quiz
curl -X POST "http://localhost:8000/api/content/lectures/$LECTURE_ID/generate-quiz" \
  -H "Content-Type: application/json" \
  -d '{"num_quiz_questions": 10}'
```

### 5c. Poll status

```bash
# In a loop (bash)
while true; do
  curl -s "http://localhost:8000/api/content/lectures/$LECTURE_ID/generation-status" | jq
  sleep 5
done
```

Watch for `"status": "completed"`

### 5d. Get materials

```bash
# Get notes
curl "http://localhost:8000/api/content/lectures/$LECTURE_ID/notes" | jq -r '.notes_markdown' > notes.md

# Get quiz
curl "http://localhost:8000/api/content/lectures/$LECTURE_ID/comprehensive-quiz" | jq > quiz.json

# Get coverage report
curl "http://localhost:8000/api/content/lectures/$LECTURE_ID/coverage-report" | jq '.overall_assessment'
```

## That's It! 🎉

You now have:
- ✅ Database tables created
- ✅ Content generation working
- ✅ API endpoints operational
- ✅ Test materials generated

## Next Steps

### For Development:

1. **Adjust Prompts**
   - Edit files in `backend/prompts/`
   - Regenerate to see improvements

2. **Test Different Lectures**
   - Try various subjects
   - Check quality across domains

3. **Monitor Costs**
   - Check DeepSeek API dashboard
   - ~$0.30 per lecture

### For Production:

1. **Frontend Integration**
   - See `USAGE_EXAMPLE.md` for React code
   - Implement status polling
   - Display materials

2. **Batch Processing**
   - Process entire courses overnight
   - Use shell scripts from `USAGE_EXAMPLE.md`

3. **Quality Review**
   - Check coverage reports
   - Iterate on prompts
   - Gather user feedback

## Common Issues

### "Migration already run"
```
ERROR - Migration 002_add_content_generation.sql failed: relation "lecture_outlines" already exists
```
✅ This is fine - tables already exist. Skip migration.

### "No transcript found"
```
ERROR: No transcript found for lecture {id}
```
❌ Lecture hasn't been processed yet. Process it first via `/api/lectures`

### "LLM API error"
```
ERROR: DeepSeek API error: 401 - Unauthorized
```
❌ Check your `DEEPSEEK_API_KEY` in `.env` or `config.yaml`

### "JSON parsing failed"
```
ERROR: LLM response is not valid JSON
```
✅ Code handles this automatically (extracts from markdown). If persists, check prompt clarity.

## Cost Estimate

**Per lecture (~110 minutes):**
- Processing: ~$0.54 (Whisper)
- Content generation: ~$0.30 (DeepSeek)
- **Total: ~$0.84**

**For a 13-lecture course:**
- Total: ~$11

## Documentation

Full docs available:

- **`IMPLEMENTATION_SUMMARY.md`** - What was built
- **`CONTENT_GENERATION.md`** - Technical reference
- **`USAGE_EXAMPLE.md`** - Code examples
- **`QUICKSTART.md`** - This guide

## Support

If you encounter issues:

1. Check logs: `logs/content_generation/`
2. Review error messages in API responses
3. Verify database connection
4. Test API keys with simple requests
5. Check prompt files exist in `backend/prompts/`

---

**Ready to generate comprehensive study materials!** 🚀
