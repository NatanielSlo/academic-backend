"""
Database migration runner.
Applies SQL migrations to the database.
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.database import DatabaseService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def run_migration(migration_file: Path, db: DatabaseService):
    """Run a single migration file."""
    logger.info(f"Running migration: {migration_file.name}")

    # Read migration SQL
    sql = migration_file.read_text(encoding='utf-8')

    # Execute migration
    conn = db._get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        cursor.close()
        logger.info(f"✓ Migration {migration_file.name} completed successfully")
    except Exception as e:
        conn.rollback()
        logger.error(f"✗ Migration {migration_file.name} failed: {e}")
        raise
    finally:
        db._put_conn(conn)


def main():
    """Run all pending migrations."""
    migrations_dir = Path(__file__).parent / "migrations"

    if not migrations_dir.exists():
        logger.error(f"Migrations directory not found: {migrations_dir}")
        return 1

    # Get all .sql files sorted by name
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        logger.info("No migration files found")
        return 0

    logger.info(f"Found {len(migration_files)} migration(s)")

    # Initialize database service
    db = DatabaseService()

    for migration_file in migration_files:
        try:
            run_migration(migration_file, db)
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return 1

    logger.info(f"\n✓ All {len(migration_files)} migration(s) completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
