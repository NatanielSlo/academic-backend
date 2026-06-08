# Supabase Setup Instructions

## 1. Create Supabase Project

1. Go to https://supabase.com/dashboard
2. Click "New Project"
3. Fill in:
   - Name: `academic-assistant` (or your choice)
   - Database Password: Choose a strong password (SAVE THIS!)
   - Region: Choose closest to you
   - Pricing Plan: Free tier is fine for MVP
4. Wait for project to be created (~2 minutes)

## 2. Enable pgvector Extension

1. In your Supabase project dashboard, go to **Database** → **Extensions**
2. Search for `vector`
3. Enable the `vector` extension (click the toggle)

## 3. Run Migration

1. In Supabase dashboard, go to **SQL Editor**
2. Click **New Query**
3. Copy the contents of `migrations/001_initial_schema.sql`
4. Paste into the SQL editor
5. Click **Run** (or press Ctrl+Enter)
6. Verify tables were created: Go to **Database** → **Tables**
   - You should see: `lectures`, `lecture_chunks`, `quizzes`, `quiz_attempts`

## 4. Get Connection String

1. In Supabase dashboard, go to **Project Settings** (gear icon) → **Database**
2. Scroll to **Connection string** section
3. Select **URI** tab
4. Copy the connection string (it looks like):
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.[project-ref].supabase.co:5432/postgres
   ```
5. Replace `[YOUR-PASSWORD]` with the database password you set in step 1

## 5. Update Environment Variables

Create or update `backend/.env` file:

```env
# Supabase
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.[project-ref].supabase.co:5432/postgres

# OpenAI (for embeddings and Whisper)
OPENAI_API_KEY=sk-...

# Groq (for fast Whisper transcription)
GROQ_API_KEY=gsk_...

# DeepSeek (for LLM)
DEEPSEEK_API_KEY=sk-...
```

## 6. Install Dependencies

```bash
cd backend
pip install supabase psycopg2-binary
```

## 7. Test Connection

Run the test script to verify database connection:

```bash
python -m app.services.database
```

You should see: "✓ Database connection successful!"

## Notes

- **Free tier limits**: 500 MB database, 2 GB bandwidth/month, 50 MB file storage
- **Vector index**: The ivfflat index will be built once you have >100 rows in `lecture_chunks`
- **Connection pooling**: Supabase handles this automatically
- **Backups**: Free tier includes daily backups (7 day retention)

## Troubleshooting

### "extension vector does not exist"
→ Enable pgvector extension in Supabase dashboard (step 2)

### "connection refused"
→ Check DATABASE_URL format and password

### "too many connections"
→ Free tier has 60 connection limit. Close unused connections or use connection pooling.
