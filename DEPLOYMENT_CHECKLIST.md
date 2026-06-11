# Deployment Checklist - Content Generation

## Pre-Deployment Testing

### ✅ Database Migration
- [ ] `python run_migration.py` succeeds
- [ ] All 5 tables created:
  - [ ] `lecture_outlines`
  - [ ] `lecture_notes`
  - [ ] `comprehensive_quizzes`
  - [ ] `coverage_reports`
  - [ ] `content_generation_status`
- [ ] Indexes created successfully
- [ ] No constraint violations

### ✅ Local Testing
- [ ] `test_content_generation.py` completes successfully
- [ ] Outline generated (Pass 1)
- [ ] Notes generated (Pass 2a)
- [ ] Quiz generated (Pass 2b)
- [ ] Coverage report generated (Pass 3)
- [ ] All files saved to `logs/content_generation/`
- [ ] Output quality is acceptable

### ✅ API Testing
- [ ] Server starts: `uvicorn app.main:app --reload`
- [ ] Health check: `GET /health` returns 200
- [ ] All 7 endpoints registered:
  - [ ] `POST /api/content/lectures/{id}/generate`
  - [ ] `GET /api/content/lectures/{id}/generation-status`
  - [ ] `GET /api/content/lectures/{id}/outline`
  - [ ] `GET /api/content/lectures/{id}/notes`
  - [ ] `GET /api/content/lectures/{id}/comprehensive-quiz`
  - [ ] `GET /api/content/lectures/{id}/coverage-report`
  - [ ] `GET /api/content/lectures/{id}/all-materials`
- [ ] Background task completes
- [ ] Status polling works
- [ ] Error handling works (invalid lecture_id)

### ✅ Integration Testing
- [ ] Process a lecture via `/api/lectures`
- [ ] Wait for lecture processing to complete
- [ ] Generate materials via `/api/content/lectures/{id}/generate`
- [ ] Poll status until complete
- [ ] Retrieve all materials successfully
- [ ] Materials quality acceptable

### ✅ Prompt Quality
- [ ] Review generated outline structure
- [ ] Check notes formatting (Markdown valid)
- [ ] Verify quiz questions make sense
- [ ] Ensure coverage report is accurate
- [ ] No hallucinations detected
- [ ] Technical terms correct

### ✅ Error Handling
- [ ] Invalid lecture_id → 404 error
- [ ] Lecture not processed → 400 error
- [ ] LLM API failure → status "failed"
- [ ] JSON parsing errors handled
- [ ] Database errors logged

### ✅ Performance
- [ ] Generation completes in ~2-3 minutes
- [ ] Database queries optimized (indexed columns)
- [ ] No memory leaks during long runs
- [ ] Background tasks don't block API

## Configuration Verification

### ✅ Environment Variables
- [ ] `DEEPSEEK_API_KEY` set and valid
- [ ] `OPENAI_API_KEY` set and valid (for Whisper)
- [ ] `DATABASE_URL` correct
- [ ] Keys have sufficient credits

### ✅ Config Files
- [ ] `config.yaml` exists
- [ ] LLM provider set to "deepseek"
- [ ] Models configured:
  - [ ] `simple: "deepseek-v4-flash"`
  - [ ] `complex: "deepseek-v4-pro"`
- [ ] API endpoints correct

### ✅ Prompts
- [ ] All 4 prompt files exist:
  - [ ] `prompts/outline_extraction.txt`
  - [ ] `prompts/notes_generation.txt`
  - [ ] `prompts/quiz_generation.txt`
  - [ ] `prompts/coverage_verification.txt`
- [ ] Prompts load successfully
- [ ] No syntax errors in prompts

### ✅ Directories
- [ ] `logs/content_generation/` exists
- [ ] Write permissions OK
- [ ] Logs being written

## Production Deployment

### ✅ Render Setup (or your hosting)
- [ ] PostgreSQL addon enabled
- [ ] Environment variables set in dashboard
- [ ] Database migration run on production DB
- [ ] Service deployed successfully
- [ ] Health check endpoint accessible

### ✅ Database (Production)
- [ ] Connection string correct
- [ ] SSL mode enabled if required
- [ ] Tables created via migration
- [ ] Indexes built
- [ ] Query performance acceptable

### ✅ Monitoring
- [ ] Logging configured
- [ ] Error tracking set up (Sentry, etc.)
- [ ] Cost tracking enabled (DeepSeek dashboard)
- [ ] API rate limits understood
- [ ] Database size monitored

### ✅ Security
- [ ] API keys not exposed in code
- [ ] CORS configured appropriately
- [ ] SQL injection prevented (parameterized queries)
- [ ] Input validation on all endpoints
- [ ] Error messages don't leak sensitive info

## Post-Deployment

### ✅ Smoke Tests
- [ ] Process 1 test lecture end-to-end
- [ ] Generate materials successfully
- [ ] Retrieve materials via API
- [ ] Check database records created
- [ ] Verify logs captured

### ✅ Frontend Integration
- [ ] Frontend can call all endpoints
- [ ] Status polling implemented
- [ ] Error messages displayed
- [ ] Materials rendered correctly
- [ ] User experience smooth

### ✅ Cost Monitoring
- [ ] Initial costs tracked
- [ ] Budget alerts set up
- [ ] Usage patterns understood
- [ ] Cost per lecture validated (~$0.30)

### ✅ Documentation
- [ ] Team trained on new features
- [ ] API documentation updated
- [ ] Known limitations communicated
- [ ] Support process defined

## Rollback Plan

If issues arise:

### Option 1: Disable Feature
```sql
-- Temporarily disable by removing status
DELETE FROM content_generation_status;
```
Frontend can check if generation is available.

### Option 2: Rollback Migration
```sql
DROP TABLE IF EXISTS content_generation_status CASCADE;
DROP TABLE IF EXISTS coverage_reports CASCADE;
DROP TABLE IF EXISTS comprehensive_quizzes CASCADE;
DROP TABLE IF EXISTS lecture_notes CASCADE;
DROP TABLE IF EXISTS lecture_outlines CASCADE;
```
Comment out content router in `main.py`.

### Option 3: Fix Forward
- Deploy prompt fixes
- Adjust model parameters
- Increase timeouts
- Scale resources

## Success Criteria

Deployment is successful when:

✅ **Functionality**
- Materials generated for test lectures
- Quality meets expectations
- No crashes or errors
- Performance acceptable

✅ **Reliability**
- Background tasks complete reliably
- Status updates accurate
- Error handling works
- Database consistent

✅ **Cost**
- Within budget (~$0.30/lecture)
- No unexpected charges
- API rate limits respected

✅ **User Experience**
- Fast enough (2-3 min acceptable)
- Clear status updates
- High-quality output
- Easy to use

## Sign-Off

- [ ] **Developer**: Tested locally, all checks pass
- [ ] **QA**: Integration tests pass, no critical bugs
- [ ] **Stakeholder**: Quality acceptable, meets requirements
- [ ] **Ops**: Deployed successfully, monitoring active

---

**Date:** _____________

**Deployed by:** _____________

**Version:** _____________

**Notes:**
