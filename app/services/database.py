import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, date
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from psycopg2.pool import SimpleConnectionPool
import json

from app.config import config

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Raised when database operations fail."""
    pass


class DatabaseService:
    """Service for PostgreSQL/Supabase database operations."""

    def __init__(self):
        """Initialize database connection pool."""
        self.pool = None
        self._init_pool()

    def _init_pool(self):
        """Create connection pool."""
        try:
            self.pool = SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=config.database.url
            )
            logger.info("Database connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise DatabaseError(f"Database connection failed: {e}")

    def _get_conn(self):
        """Get a connection from the pool."""
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")
        return self.pool.getconn()

    def _put_conn(self, conn):
        """Return a connection to the pool."""
        if self.pool:
            self.pool.putconn(conn)

    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
                return True
            finally:
                self._put_conn(conn)
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    # ==================== LECTURE OPERATIONS ====================

    def create_lecture(
        self,
        url: str,
        course_name: Optional[str] = None,
        lecture_number: Optional[str] = None,
        lecture_date: Optional[date] = None
    ) -> str:
        """
        Create a new lecture record.

        Returns:
            lecture_id (UUID as string)
        """
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO lectures (url, course_name, lecture_number, date, status, progress_percent)
                    VALUES (%s, %s, %s, %s, 'processing', 0)
                    RETURNING id
                    """,
                    (url, course_name, lecture_number, lecture_date)
                )
                result = cur.fetchone()
                conn.commit()
                lecture_id = str(result['id'])
                logger.info(f"Created lecture {lecture_id}")
                return lecture_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create lecture: {e}")
            raise DatabaseError(f"Failed to create lecture: {e}")
        finally:
            self._put_conn(conn)

    def update_lecture_status(
        self,
        lecture_id: str,
        status: str,
        progress_percent: Optional[int] = None,
        error_message: Optional[str] = None,
        progress_message: Optional[str] = None
    ):
        """
        Update lecture processing status.

        Only the columns whose arguments are provided get written, so a fine-grained
        progress tick (status + progress_percent + progress_message) doesn't clobber
        a previously-set error_message, and vice versa.
        """
        conn = self._get_conn()
        try:
            sets = ["status = %s"]
            params: list = [status]

            if progress_percent is not None:
                sets.append("progress_percent = %s")
                params.append(progress_percent)
            if progress_message is not None:
                sets.append("progress_message = %s")
                params.append(progress_message)
            if error_message is not None:
                sets.append("error_message = %s")
                params.append(error_message)

            params.append(lecture_id)
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE lectures SET {', '.join(sets)} WHERE id = %s",
                    params
                )
                conn.commit()
                logger.info(f"Updated lecture {lecture_id} status to {status}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update lecture status: {e}")
            raise DatabaseError(f"Failed to update lecture status: {e}")
        finally:
            self._put_conn(conn)

    def update_lecture_audio_path(self, lecture_id: str, audio_path: str):
        """Update lecture audio file path."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE lectures SET audio_path = %s WHERE id = %s",
                    (audio_path, lecture_id)
                )
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update audio path: {e}")
            raise DatabaseError(f"Failed to update audio path: {e}")
        finally:
            self._put_conn(conn)

    def save_transcript(self, lecture_id: str, transcript: List[Dict[str, Any]]):
        """
        Save full transcript for a lecture.

        Args:
            lecture_id: The lecture ID
            transcript: List of {timestamp, timestamp_seconds, text} dicts
        """
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE lectures SET full_transcript = %s WHERE id = %s",
                    (Json(transcript), lecture_id)
                )
                conn.commit()
                logger.info(f"Saved transcript for lecture {lecture_id} ({len(transcript)} segments)")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save transcript: {e}")
            raise DatabaseError(f"Failed to save transcript: {e}")
        finally:
            self._put_conn(conn)

    def save_cleaned_transcript(self, lecture_id: str, transcript: List[Dict[str, Any]]):
        """
        Save the LLM-cleaned transcript for a lecture.

        Args:
            lecture_id: The lecture ID
            transcript: List of {timestamp, timestamp_seconds, text} dicts (cleaned)
        """
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE lectures SET cleaned_transcript = %s WHERE id = %s",
                    (Json(transcript), lecture_id)
                )
                conn.commit()
                logger.info(f"Saved cleaned transcript for lecture {lecture_id} ({len(transcript)} segments)")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save cleaned transcript: {e}")
            raise DatabaseError(f"Failed to save cleaned transcript: {e}")
        finally:
            self._put_conn(conn)

    def get_lecture(self, lecture_id: str) -> Optional[Dict[str, Any]]:
        """Get lecture by ID."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, url, course_name, lecture_number, date,
                           status, progress_percent, error_message, progress_message,
                           full_transcript, cleaned_transcript, audio_path, created_at, updated_at
                    FROM lectures
                    WHERE id = %s
                    """,
                    (lecture_id,)
                )
                result = cur.fetchone()
                if result:
                    return dict(result)
                return None
        except Exception as e:
            logger.error(f"Failed to get lecture: {e}")
            raise DatabaseError(f"Failed to get lecture: {e}")
        finally:
            self._put_conn(conn)

    def list_lectures(self) -> List[Dict[str, Any]]:
        """List all lectures."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, url, course_name, lecture_number, date,
                           status, created_at
                    FROM lectures
                    ORDER BY created_at DESC
                    """
                )
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Failed to list lectures: {e}")
            raise DatabaseError(f"Failed to list lectures: {e}")
        finally:
            self._put_conn(conn)

    # ==================== CHUNK OPERATIONS ====================

    def save_chunks(
        self,
        lecture_id: str,
        chunks: List[Dict[str, Any]]
    ):
        """
        Save text chunks with embeddings.

        Args:
            lecture_id: The lecture ID
            chunks: List of dicts with keys: chunk_index, text, start_timestamp_seconds,
                    end_timestamp_seconds, embedding
        """
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                for chunk in chunks:
                    # Convert embedding list to pgvector format
                    embedding_str = '[' + ','.join(map(str, chunk['embedding'])) + ']'

                    cur.execute(
                        """
                        INSERT INTO lecture_chunks
                        (lecture_id, chunk_index, text, start_timestamp_seconds,
                         end_timestamp_seconds, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s::vector)
                        """,
                        (
                            lecture_id,
                            chunk['chunk_index'],
                            chunk['text'],
                            chunk.get('start_timestamp_seconds'),
                            chunk.get('end_timestamp_seconds'),
                            embedding_str
                        )
                    )
                conn.commit()
                logger.info(f"Saved {len(chunks)} chunks for lecture {lecture_id}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save chunks: {e}")
            raise DatabaseError(f"Failed to save chunks: {e}")
        finally:
            self._put_conn(conn)

    def search_similar_chunks(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        lecture_id: Optional[str] = None,
        course_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar chunks using vector similarity.

        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            lecture_id: Optional filter by lecture
            course_name: Optional filter by course

        Returns:
            List of chunks with similarity scores
        """
        conn = self._get_conn()
        try:
            embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'

            logger.debug(f"search_similar_chunks called: top_k={top_k}, lecture_id={lecture_id}, course_name={course_name}")
            logger.debug(f"Query embedding: {len(query_embedding)} dims, first 3 values: {query_embedding[:3]}")

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Build query with optional filters
                query = """
                    SELECT
                        c.id,
                        c.lecture_id,
                        c.text,
                        c.start_timestamp_seconds,
                        c.end_timestamp_seconds,
                        l.course_name,
                        l.lecture_number,
                        l.url,
                        1 - (c.embedding <=> %s::vector) as similarity
                    FROM lecture_chunks c
                    JOIN lectures l ON c.lecture_id = l.id
                    WHERE 1=1
                """
                params = [embedding_str]

                if lecture_id:
                    query += " AND c.lecture_id = %s"
                    params.append(lecture_id)

                if course_name:
                    query += " AND l.course_name = %s"
                    params.append(course_name)

                query += """
                    ORDER BY c.embedding <=> %s::vector
                    LIMIT %s
                """
                params.extend([embedding_str, top_k])

                logger.debug(f"Executing query with {len(params)} params")
                logger.debug(f"Query filters: lecture_id={lecture_id}, course_name={course_name}, top_k={top_k}")

                cur.execute(query, params)
                results = cur.fetchall()

                logger.debug(f"Query returned {len(results)} results")
                if results:
                    logger.debug(f"First result similarity: {results[0].get('similarity', 'N/A')}")

                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Failed to search chunks: {e}", exc_info=True)
            raise DatabaseError(f"Failed to search chunks: {e}")
        finally:
            self._put_conn(conn)

    # ==================== QUIZ OPERATIONS ====================

    def create_quiz(
        self,
        lecture_id: str,
        questions: List[Dict[str, Any]]
    ) -> str:
        """
        Create a new quiz.

        Args:
            lecture_id: The lecture ID
            questions: List of question dicts

        Returns:
            quiz_id (UUID as string)
        """
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO quizzes (lecture_id, questions)
                    VALUES (%s, %s)
                    RETURNING id
                    """,
                    (lecture_id, Json(questions))
                )
                result = cur.fetchone()
                conn.commit()
                quiz_id = str(result['id'])
                logger.info(f"Created quiz {quiz_id} for lecture {lecture_id}")
                return quiz_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create quiz: {e}")
            raise DatabaseError(f"Failed to create quiz: {e}")
        finally:
            self._put_conn(conn)

    def get_quiz(self, quiz_id: str) -> Optional[Dict[str, Any]]:
        """Get quiz by ID."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, lecture_id, questions, created_at FROM quizzes WHERE id = %s",
                    (quiz_id,)
                )
                result = cur.fetchone()
                if result:
                    return dict(result)
                return None
        except Exception as e:
            logger.error(f"Failed to get quiz: {e}")
            raise DatabaseError(f"Failed to get quiz: {e}")
        finally:
            self._put_conn(conn)

    def save_quiz_attempt(
        self,
        quiz_id: str,
        score: int,
        total: int,
        answers: Dict[str, str]
    ) -> str:
        """Save a quiz attempt."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO quiz_attempts (quiz_id, score, total, answers)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (quiz_id, score, total, Json(answers))
                )
                result = cur.fetchone()
                conn.commit()
                attempt_id = str(result['id'])
                logger.info(f"Saved quiz attempt {attempt_id} (score: {score}/{total})")
                return attempt_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save quiz attempt: {e}")
            raise DatabaseError(f"Failed to save quiz attempt: {e}")
        finally:
            self._put_conn(conn)

    def close(self):
        """Close all database connections."""
        if self.pool:
            self.pool.closeall()
            logger.info("Database connection pool closed")


# Test script
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    try:
        db = DatabaseService()
        if db.test_connection():
            print("✓ Database connection successful!")
        else:
            print("✗ Database connection failed!")
    except Exception as e:
        print(f"✗ Error: {e}")
