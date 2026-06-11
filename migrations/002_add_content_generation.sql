-- Migration: Add content generation tables (notes, outlines, coverage reports)
-- Purpose: Support three-pass content generation pipeline

-- Table for lecture outlines (Pass 1 output)
CREATE TABLE IF NOT EXISTS lecture_outlines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lecture_id UUID REFERENCES lectures(id) ON DELETE CASCADE,
    outline JSONB NOT NULL,  -- Complete structured outline
    generated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(lecture_id)  -- One outline per lecture
);

-- Index for fast lookup
CREATE INDEX IF NOT EXISTS idx_outlines_lecture_id ON lecture_outlines(lecture_id);

-- Table for generated notes (Pass 2a output)
CREATE TABLE IF NOT EXISTS lecture_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lecture_id UUID REFERENCES lectures(id) ON DELETE CASCADE,
    notes_markdown TEXT NOT NULL,  -- Full Markdown notes
    generated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(lecture_id)  -- One set of notes per lecture
);

-- Index for fast lookup
CREATE INDEX IF NOT EXISTS idx_notes_lecture_id ON lecture_notes(lecture_id);

-- Table for comprehensive quizzes (Pass 2b output)
-- Note: This is separate from the existing 'quizzes' table which may have multiple quizzes per lecture
CREATE TABLE IF NOT EXISTS comprehensive_quizzes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lecture_id UUID REFERENCES lectures(id) ON DELETE CASCADE,
    quiz_data JSONB NOT NULL,  -- Complete quiz with metadata
    num_questions INTEGER NOT NULL,
    generated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(lecture_id)  -- One comprehensive quiz per lecture
);

-- Index for fast lookup
CREATE INDEX IF NOT EXISTS idx_comprehensive_quizzes_lecture_id ON comprehensive_quizzes(lecture_id);

-- Table for coverage reports (Pass 3 output)
CREATE TABLE IF NOT EXISTS coverage_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lecture_id UUID REFERENCES lectures(id) ON DELETE CASCADE,
    report JSONB NOT NULL,  -- Complete coverage report
    coverage_percent NUMERIC(5,2) NOT NULL,  -- For easy filtering
    quality_score TEXT NOT NULL,  -- "excellent", "good", "fair", "poor"
    generated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(lecture_id)  -- One report per lecture
);

-- Indexes for filtering and sorting
CREATE INDEX IF NOT EXISTS idx_coverage_reports_lecture_id ON coverage_reports(lecture_id);
CREATE INDEX IF NOT EXISTS idx_coverage_reports_coverage ON coverage_reports(coverage_percent);
CREATE INDEX IF NOT EXISTS idx_coverage_reports_quality ON coverage_reports(quality_score);

-- Table for tracking generation status (for async processing)
CREATE TABLE IF NOT EXISTS content_generation_status (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lecture_id UUID REFERENCES lectures(id) ON DELETE CASCADE,
    status TEXT NOT NULL,  -- "not_started", "generating_outline", "generating_notes", "generating_quiz", "verifying", "completed", "failed"
    progress_percent INTEGER DEFAULT 0,
    current_step TEXT,
    error_message TEXT,
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    UNIQUE(lecture_id)  -- One status per lecture
);

-- Index for fast lookup and filtering
CREATE INDEX IF NOT EXISTS idx_content_generation_status_lecture_id ON content_generation_status(lecture_id);
CREATE INDEX IF NOT EXISTS idx_content_generation_status_status ON content_generation_status(status);

-- Add comment
COMMENT ON TABLE lecture_outlines IS 'Structured outlines extracted from lecture transcripts (Pass 1)';
COMMENT ON TABLE lecture_notes IS 'Detailed Markdown notes generated from outlines (Pass 2a)';
COMMENT ON TABLE comprehensive_quizzes IS 'Comprehensive quizzes generated from outlines (Pass 2b)';
COMMENT ON TABLE coverage_reports IS 'Coverage verification reports (Pass 3)';
COMMENT ON TABLE content_generation_status IS 'Tracks async content generation progress';
