"""Generate quiz only for a lecture that already has outline."""
import json
from app.services.content_generator import ContentGenerator
from app.services.database import DatabaseService
from psycopg2.extras import Json
from datetime import datetime

lecture_id = '8c31dfcd-1ba1-4069-baa0-88218696ed91'

# Get outline from database
db = DatabaseService()
conn = db._get_conn()
try:
    cursor = conn.cursor()
    cursor.execute("SELECT outline FROM lecture_outlines WHERE lecture_id = %s", (lecture_id,))
    result = cursor.fetchone()
    cursor.close()
finally:
    db._put_conn(conn)

if not result:
    print("ERROR: No outline found in database")
    exit(1)

outline = result[0]
print(f"Loaded outline from database: {len(json.dumps(outline))} chars")

# Generate quiz
generator = ContentGenerator()
print("\nGenerating quiz (10 questions)...")
quiz = generator.pass2_generate_quiz(
    lecture_id=lecture_id,
    outline=outline,
    num_questions=10,
    show_progress=True
)

# Save to database
conn = db._get_conn()
try:
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO comprehensive_quizzes (lecture_id, quiz_data, num_questions, generated_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (lecture_id) DO UPDATE SET
            quiz_data = EXCLUDED.quiz_data,
            num_questions = EXCLUDED.num_questions,
            generated_at = EXCLUDED.generated_at
    """, (lecture_id, Json(quiz), len(quiz['questions']), datetime.now()))
    conn.commit()
    cursor.close()
    print("\nOK: Quiz saved to database")
finally:
    db._put_conn(conn)

print("\nDONE! Access via:")
print(f"GET /api/content/lectures/{lecture_id}/comprehensive-quiz")
