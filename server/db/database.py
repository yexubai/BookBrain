"""Database engine and session management for BookBrain."""

import logging
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings
from db.models import Base

logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

# Enable WAL mode for SQLite to safely support multiple concurrent writes/reads
from sqlalchemy import event
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-100000") # Use ~100MB for cache
    cursor.close()

# Session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables and the FTS5 full-text search index."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # FTS5 virtual table for fast full-text search.
        # Indexes title, author, filename, summary, description, AND full text_content.
        # unicode61 tokenizer handles CJK and accented characters.
        
        # Check if we need to upgrade the FTS table (add text_content)
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
                    COALESCE(REPLACE(new.file_path,
                        RTRIM(new.file_path, REPLACE(new.file_path, '/', '')), ''), ''),
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
                    COALESCE(REPLACE(new.file_path,
                        RTRIM(new.file_path, REPLACE(new.file_path, '/', '')), ''), ''),
                    COALESCE(new.summary, ''),
                    COALESCE(new.description, ''),
                    COALESCE(new.text_content, '')
                );
            END
        """))


async def get_session() -> AsyncSession:
    """Get a database session (dependency injection)."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    """Close the database engine."""
    await engine.dispose()
