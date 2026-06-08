-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Lectures table
CREATE TABLE lectures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url TEXT NOT NULL,
    course_name TEXT,
    lecture_number TEXT,
    date DATE,
    status TEXT NOT NULL CHECK (status IN ('processing', 'downloading', 'transcribing', 'embedding', 'completed', 'failed')),
    progress_percent INTEGER DEFAULT 0 CHECK (progress_percent >= 0 AND progress_percent <= 100),
    error_message TEXT,
    full_transcript JSONB, -- array of {timestamp, timestamp_seconds, text}
    audio_path TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Lecture chunks for vector search
CREATE TABLE lecture_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lecture_id UUID NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    start_timestamp_seconds INTEGER,
    end_timestamp_seconds INTEGER,
    embedding vector(1536), -- text-embedding-3-small dimension
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(lecture_id, chunk_index)
);

-- Create vector similarity search index
CREATE INDEX ON lecture_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Create indexes for faster lookups
CREATE INDEX idx_lecture_chunks_lecture_id ON lecture_chunks(lecture_id);
CREATE INDEX idx_lectures_status ON lectures(status);
CREATE INDEX idx_lectures_course_name ON lectures(course_name);
CREATE INDEX idx_lectures_created_at ON lectures(created_at DESC);

-- Quizzes table
CREATE TABLE quizzes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lecture_id UUID NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    questions JSONB NOT NULL, -- array of question objects with answers
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Quiz attempts table
CREATE TABLE quiz_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quiz_id UUID NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    score INTEGER NOT NULL CHECK (score >= 0),
    total INTEGER NOT NULL CHECK (total > 0),
    answers JSONB NOT NULL, -- {question_id: user_answer}
    completed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for quizzes
CREATE INDEX idx_quizzes_lecture_id ON quizzes(lecture_id);
CREATE INDEX idx_quiz_attempts_quiz_id ON quiz_attempts(quiz_id);
CREATE INDEX idx_quiz_attempts_completed_at ON quiz_attempts(completed_at DESC);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to automatically update updated_at
CREATE TRIGGER update_lectures_updated_at BEFORE UPDATE ON lectures
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
