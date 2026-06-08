# Testing Pipeline from Existing Transcript

If you already have a transcript and want to test the rest of the pipeline (chunking → LLM cleanup → embeddings → database), use these scripts.

## Quick Start

### Option 1: Test with Sample Data (No Database)

```bash
python test_pipeline_from_transcript.py
```

When prompted "Do you want to save results to database? (y/n)", type `n`.

This will:
1. Use built-in sample transcript
2. Chunk it into segments
3. Clean with LLM (DeepSeek)
4. Generate embeddings (OpenAI)
5. Show results (no database save)

### Option 2: Test with Your Transcript File

**Step 1: Create transcript JSON file**

Your JSON file should have this format:
```json
{
  "segments": [
    {
      "start": 0.0,
      "end": 5.5,
      "text": "Hello everyone, welcome to the lecture."
    },
    {
      "start": 5.5,
      "end": 12.0,
      "text": "Today we'll talk about dynamic programming."
    }
  ]
}
```

**Step 2: Run the test**

```bash
python test_pipeline_from_transcript.py your_transcript.json
```

### Option 3: Test with Database Save

```bash
python test_pipeline_from_transcript.py
# or
python test_pipeline_from_transcript.py your_transcript.json
```

When prompted, type `y` to save to database.

This will:
1. Create a lecture record in Supabase
2. Process the transcript through full pipeline
3. Save chunks with embeddings to database
4. Mark lecture as "completed"

## Export Existing Transcript

If you have a transcript from `test_transcription.py`, you can export it:

### Method 1: In Python Code

```python
from app.services.transcription import TranscriptionService
from export_transcript import export_from_whisper_result

# Get your transcript
service = TranscriptionService()
result = service.transcribe(audio_path)

# Export to JSON
export_from_whisper_result(result)

# Now run test
# python test_pipeline_from_transcript.py transcript_export.json
```

### Method 2: Manual Export

1. Edit `export_transcript.py`
2. Paste your transcript data into `export_sample_transcript()`
3. Run: `python export_transcript.py`
4. Use the generated `transcript_export.json`

## What the Test Shows

The test script provides detailed output at each stage:

### Stage 1: Chunking
```
[STEP 1] CHUNKING
----------------------------------------------------------------------

✓ Created 3 chunks

Chunk 0:
  Time: 0s - 25s
  Tokens: 87
  Text: Um, so hello everyone, uh, welcome to...
```

### Stage 2: LLM Cleanup
```
[STEP 2] LLM CLEANUP
----------------------------------------------------------------------
[LLM] Cleaning 3 transcript chunks with LLM
Model: deepseek-v4-flash
[LLM] Chunk 1/3... ✓
[LLM] Chunk 2/3... ✓
[LLM] Chunk 3/3... ✓

BEFORE vs AFTER comparison:

Chunk 0:
  BEFORE: Um, so hello everyone, uh, welcome to, like, the first lecture...
  AFTER:  Hello everyone, welcome to the first lecture...
```

### Stage 3: Embeddings
```
[STEP 3] GENERATE EMBEDDINGS
----------------------------------------------------------------------
[EMBEDDING] Batch 1/1 (3 texts)... ✓

✓ Generated 3 embeddings
  Embedding dimension: 1536
```

### Stage 4: Database (Optional)
```
[STEP 4] SAVE TO DATABASE
----------------------------------------------------------------------

✓ Saved 3 chunks to database
  Lecture ID: 123e4567-e89b-12d3-a456-426614174000
```

## Requirements

Make sure you have:

1. **Environment variables set** (`.env` file):
   ```env
   DEEPSEEK_API_KEY=sk-...
   OPENAI_API_KEY=sk-...
   DATABASE_URL=postgresql://... (only if saving to DB)
   ```

2. **Dependencies installed**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Supabase setup** (only if saving to DB):
   - Follow `SUPABASE_SETUP.md`
   - Run migration SQL

## Troubleshooting

### "LLMError: DeepSeek API error"
- Check `DEEPSEEK_API_KEY` in `.env`
- Verify you have API credits

### "EmbeddingError: OpenAI API error"
- Check `OPENAI_API_KEY` in `.env`
- Verify API key is valid

### "DatabaseError: connection refused"
- Check `DATABASE_URL` in `.env`
- Verify Supabase is set up (see `SUPABASE_SETUP.md`)

### "Prompt file not found"
- Make sure `prompts/transcript_cleanup.txt` exists
- Run script from `backend/` directory

## Cost Estimate

For a typical 90-minute lecture (~30 chunks):

- **LLM Cleanup**: ~$0.003
- **Embeddings**: ~$0.0006
- **Total**: ~$0.004 per test run

Very cheap to test! 🎉

## Next Steps

After testing the pipeline:

1. Try editing the prompt in `prompts/transcript_cleanup.txt`
2. Compare before/after cleanup quality
3. Test with real lecture transcripts
4. Integrate into full API pipeline

## Files

- `test_pipeline_from_transcript.py` - Main test script
- `export_transcript.py` - Helper to export transcripts to JSON
- `prompts/transcript_cleanup.txt` - LLM cleanup prompt (editable)
