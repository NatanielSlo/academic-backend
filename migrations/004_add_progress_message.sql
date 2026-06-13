-- Human-readable, fine-grained progress detail for the processing pipeline.
-- progress_percent gives the coarse number; progress_message describes the
-- current sub-step (e.g. "Downloading audio: 45%", "Cleaning transcript: 42/130")
-- so the frontend can show what is actually happening during the long steps.
ALTER TABLE lectures ADD COLUMN IF NOT EXISTS progress_message TEXT;
