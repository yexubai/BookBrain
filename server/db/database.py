"""Database engine and session management for BookBrain."""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings
from db.models import Base

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

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
        # Indexes title, author, filename (stem of file_path), summary, description.
        # unicode61 tokenizer handles CJK and accented characters.
        await conn.execute(__import__("sqlalchemy").text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
                title, author, filename, summary, description,
                content='books', content_rowid='id',
                tokenize='unicode61'
            )
        """))
        # Triggers keep the FTS index in sync with the books table automatically.
        await conn.execute(__import__("sqlalchemy").text("""
            CREATE TRIGGER IF NOT EXISTS books_fts_ai AFTER INSERT ON books BEGIN
                INSERT INTO books_fts(rowid, title, author, filename, summary, description)
                VALUES (
                    new.id,
                    COALESCE(new.title, ''),
                    COALESCE(new.author, ''),
                    COALESCE(REPLACE(new.file_path,
                        RTRIM(new.file_path, REPLACE(new.file_path, '/', '')), ''), ''),
                    COALESCE(new.summary, ''),
                    COALESCE(new.description, '')
                );
            END
        """))
        await conn.execute(__import__("sqlalchemy").text("""
            CREATE TRIGGER IF NOT EXISTS books_fts_ad AFTER DELETE ON books BEGIN
                INSERT INTO books_fts(books_fts, rowid, title, author, filename, summary, description)
                VALUES ('delete', old.id, COALESCE(old.title,''), COALESCE(old.author,''),
                    '', COALESCE(old.summary,''), COALESCE(old.description,''));
            END
        """))
        await conn.execute(__import__("sqlalchemy").text("""
            CREATE TRIGGER IF NOT EXISTS books_fts_au AFTER UPDATE ON books BEGIN
                INSERT INTO books_fts(books_fts, rowid, title, author, filename, summary, description)
                VALUES ('delete', old.id, COALESCE(old.title,''), COALESCE(old.author,''),
                    '', COALESCE(old.summary,''), COALESCE(old.description,''));
                INSERT INTO books_fts(rowid, title, author, filename, summary, description)
                VALUES (
                    new.id,
                    COALESCE(new.title, ''),
                    COALESCE(new.author, ''),
                    COALESCE(REPLACE(new.file_path,
                        RTRIM(new.file_path, REPLACE(new.file_path, '/', '')), ''), ''),
                    COALESCE(new.summary, ''),
                    COALESCE(new.description, '')
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
