"""Database engine and session management for BookBrain.

Provides:
  - An async SQLAlchemy engine (SQLite + aiosqlite by default)
  - A session factory for dependency injection in FastAPI routes
  - ``init_db()`` which creates all ORM tables plus FTS5 virtual tables
    and their synchronisation triggers
  - SQLite performance pragmas (WAL mode, enlarged page cache)
"""

import logging
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings
from db.models import Base

logger = logging.getLogger(__name__)

# ─── Async Engine ──────────────────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,  # Log all SQL statements when debug is on
    future=True,
)

# ─── SQLite Performance Pragmas ────────────────────────────────
# Applied on every new raw DBAPI connection (before SQLAlchemy uses it).
from sqlalchemy import event
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Configure SQLite for better concurrency and performance.

    - WAL (Write-Ahead Logging): allows concurrent readers while writing
    - synchronous=NORMAL: safe with WAL, reduces fsync overhead
    - cache_size=-100000: use ~100 MB of memory for the page cache
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-100000")
    cursor.close()

# ─── Session Factory ───────────────────────────────────────────
# expire_on_commit=False prevents lazy-load issues when accessing
# attributes after the session is committed.
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all ORM tables and FTS5 full-text search virtual tables.

    FTS5 setup includes:
      - ``books_fts``:  indexes title, author, filename, summary, description,
        and full text_content for book-level search
      - ``chunks_fts``: indexes chunk content for page-level deep search
      - Auto-sync triggers (INSERT/UPDATE/DELETE) to keep FTS tables in sync
        with the source tables without manual maintenance
      - ``unicode61`` tokenizer for proper CJK and accented character handling
    """
    async with engine.begin() as conn:
        # Create all ORM-declared tables (books, chunks, annotations)
        await conn.run_sync(Base.metadata.create_all)

        # --- books_fts: book-level full-text index ---
        # Check if the existing FTS table needs upgrading (e.g. missing text_content column)
        res = await conn.execute(__import__("sqlalchemy").text("PRAGMA table_info(books_fts)"))
        columns = [row[1] for row in res.fetchall()]
        if columns and "text_content" not in columns:
            logger.info("Upgrading FTS table to include text_content...")
            await conn.execute(__import__("sqlalchemy").text("DROP TABLE books_fts"))
            
        await conn.execute(__import__("sqlalchemy").text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
                title, author, filename, summary, description, text_content,
                content='books', content_rowid='id',
                tokenize='unicode61'
            )
        """))
        await conn.execute(__import__("sqlalchemy").text("""
            CREATE TRIGGER IF NOT EXISTS books_fts_ai AFTER INSERT ON books BEGIN
                INSERT INTO books_fts(rowid, title, author, filename, summary, description, text_content)
                VALUES (
                    new.id,
                    COALESCE(new.title, ''),
                    COALESCE(new.author, ''),
                    COALESCE(
                        CASE
                            WHEN INSTR(new.file_path, '/') >= INSTR(new.file_path, CHAR(92))
                                AND INSTR(new.file_path, '/') > 0
                            THEN REPLACE(new.file_path,
                                    RTRIM(new.file_path, REPLACE(new.file_path, '/', '')), '')
                            WHEN INSTR(new.file_path, CHAR(92)) > 0
                            THEN REPLACE(new.file_path,
                                    RTRIM(new.file_path, REPLACE(new.file_path, CHAR(92), '')), '')
                            ELSE new.file_path
                        END,
                    ''),
                    COALESCE(new.summary, ''),
                    COALESCE(new.description, ''),
                    COALESCE(new.text_content, '')
                );
            END
        """))
        await conn.execute(__import__("sqlalchemy").text("""
            CREATE TRIGGER IF NOT EXISTS books_fts_ad AFTER DELETE ON books BEGIN
                INSERT INTO books_fts(books_fts, rowid, title, author, filename, summary, description, text_content)
                VALUES ('delete', old.id, COALESCE(old.title,''), COALESCE(old.author,''),
                    '', COALESCE(old.summary,''), COALESCE(old.description,''), COALESCE(old.text_content,''));
            END
        """))
        await conn.execute(__import__("sqlalchemy").text("""
            CREATE TRIGGER IF NOT EXISTS books_fts_au AFTER UPDATE ON books BEGIN
                INSERT INTO books_fts(books_fts, rowid, title, author, filename, summary, description, text_content)
                VALUES ('delete', old.id, COALESCE(old.title,''), COALESCE(old.author,''),
                    '', COALESCE(old.summary,''), COALESCE(old.description,''), COALESCE(old.text_content,''));
                INSERT INTO books_fts(rowid, title, author, filename, summary, description, text_content)
                VALUES (
                    new.id,
                    COALESCE(new.title, ''),
                    COALESCE(new.author, ''),
                    COALESCE(
                        CASE
                            WHEN INSTR(new.file_path, '/') >= INSTR(new.file_path, CHAR(92))
                                AND INSTR(new.file_path, '/') > 0
                            THEN REPLACE(new.file_path,
                                    RTRIM(new.file_path, REPLACE(new.file_path, '/', '')), '')
                            WHEN INSTR(new.file_path, CHAR(92)) > 0
                            THEN REPLACE(new.file_path,
                                    RTRIM(new.file_path, REPLACE(new.file_path, CHAR(92), '')), '')
                            ELSE new.file_path
                        END,
                    ''),
                    COALESCE(new.summary, ''),
                    COALESCE(new.description, ''),
                    COALESCE(new.text_content, '')
                );
            END
        """))

        # --- chunks_fts: page/chapter-level full-text index ---
        try:
            await conn.execute(__import__("sqlalchemy").text("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    content,
                    content='chunks', content_rowid='id',
                    tokenize='unicode61'
                )
            """))
            
            # Populate chunks_fts if it's empty but chunks exist
            res = await conn.execute(__import__("sqlalchemy").text("SELECT COUNT(*) FROM chunks_fts"))
            if res.scalar() == 0:
                logger.info("Populating chunks_fts index for the first time...")
                await conn.execute(__import__("sqlalchemy").text("""
                    INSERT INTO chunks_fts(rowid, content)
                    SELECT id, content FROM chunks
                """))
        except Exception as e:
            logger.warning("FTS table chunks_fts initialization skipped or failed: %s", e)

        # Auto-sync triggers for chunks_fts (created individually for safety)
        try:
            await conn.execute(__import__("sqlalchemy").text("""
                CREATE TRIGGER IF NOT EXISTS chunks_fts_ai AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunks_fts(rowid, content) VALUES (new.id, new.content);
                END;
            """))
            await conn.execute(__import__("sqlalchemy").text("""
                CREATE TRIGGER IF NOT EXISTS chunks_fts_ad AFTER DELETE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.id, old.content);
                END;
            """))
            await conn.execute(__import__("sqlalchemy").text("""
                CREATE TRIGGER IF NOT EXISTS chunks_fts_au AFTER UPDATE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.id, old.content);
                    INSERT INTO chunks_fts(rowid, content) VALUES (new.id, new.content);
                END;
            """))
        except Exception as e:
            logger.warning("FTS triggers for chunks_fts creation failed: %s", e)


async def get_session() -> AsyncSession:
    """FastAPI dependency that provides a database session.

    Automatically commits on success and rolls back on exception.
    Used via ``Depends(get_session)`` in route handlers.
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    """Dispose of the database engine and release all connections.

    Called during application shutdown.
    """
    await engine.dispose()
