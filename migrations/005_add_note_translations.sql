-- Migration: Add translated notes table
-- Purpose: Store translations of the German lecture notes (e.g. Polish, English).
-- The source notes live in lecture_notes (one German set per lecture, UNIQUE(lecture_id));
-- translations are keyed additionally by target language so a lecture can have several.

CREATE TABLE IF NOT EXISTS lecture_note_translations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lecture_id UUID REFERENCES lectures(id) ON DELETE CASCADE,
    language TEXT NOT NULL,            -- target language code: 'pl', 'en'
    notes_markdown TEXT NOT NULL,      -- translated Markdown notes
    source_language TEXT DEFAULT 'de', -- language the notes were translated from
    generated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(lecture_id, language)       -- one translation per (lecture, language)
);

-- Index for fast lookup
CREATE INDEX IF NOT EXISTS idx_note_translations_lecture_id ON lecture_note_translations(lecture_id);

COMMENT ON TABLE lecture_note_translations IS 'Translations of the German lecture notes into other languages (pl, en)';
