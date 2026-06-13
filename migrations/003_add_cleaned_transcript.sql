-- Migration: Add cleaned transcript column
-- Purpose: Store the LLM-cleaned transcript (filler/repetitions removed, punctuation
--          and technical terms corrected) so the frontend can display it and content
--          generation (outline/notes/quiz) can build from clean text instead of raw ASR.
-- The raw `full_transcript` is kept for exact reference and timestamps.

ALTER TABLE lectures
    ADD COLUMN IF NOT EXISTS cleaned_transcript JSONB;

COMMENT ON COLUMN lectures.cleaned_transcript IS
    'LLM-cleaned transcript as a list of {timestamp, timestamp_seconds, text} entries (same shape as full_transcript). Source of truth for content generation and frontend display.';
