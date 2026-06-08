-- Fix pgvector index issue
-- The IVFFlat index with lists=100 doesn't work correctly for small datasets
-- For datasets < 1000 chunks, sequential scan is faster and more reliable

-- Drop the problematic index
DROP INDEX IF EXISTS lecture_chunks_embedding_idx;

-- Note: For larger datasets (1000+ chunks), recreate with appropriate parameters:
-- For < 1000 chunks: Use sequential scan (no index) or HNSW
-- For > 1000 chunks: Use IVFFlat with lists = rows / 1000
-- For > 10000 chunks: Use IVFFlat with lists = SQRT(rows)

-- Example for future when you have more data:
-- CREATE INDEX lecture_chunks_embedding_idx
-- ON lecture_chunks
-- USING hnsw (embedding vector_cosine_ops)
-- WITH (m = 16, ef_construction = 64);

-- Or for very large datasets:
-- CREATE INDEX lecture_chunks_embedding_idx
-- ON lecture_chunks
-- USING ivfflat (embedding vector_cosine_ops)
-- WITH (lists = 100);
