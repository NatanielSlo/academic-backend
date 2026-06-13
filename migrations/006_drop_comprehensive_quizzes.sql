-- Migration: Drop the comprehensive_quizzes table.
-- Generated quizzes now live in the original `quizzes` table (one row per generation,
-- history preserved) and attempts in `quiz_attempts`. See app/api/content.py.

DROP TABLE IF EXISTS comprehensive_quizzes;
