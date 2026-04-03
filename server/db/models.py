"""SQLAlchemy database models for BookBrain."""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, Index, ForeignKey
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class Book(Base):
    """Ebook metadata model.

    text_content is stored in a separate BookContent table so that list
    queries (which never need the full text) don't pay the cost of loading
    tens of kilobytes per row.
    """

    __tablename__ = "books"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Basic metadata
    title = Column(String(500), nullable=False, index=True)
    author = Column(String(500), default="Unknown")
    isbn = Column(String(20), default=None)
    publisher = Column(String(300), default=None)
    year = Column(Integer, default=None)
    language = Column(String(10), default=None)
    description = Column(Text, default=None)

    # File info
    format = Column(String(10), nullable=False)
    file_path = Column(String(1000), nullable=False, unique=True)
    file_size = Column(Integer, default=0)
    file_hash = Column(String(64), default=None, index=True)

    # Cover
    cover_path = Column(String(1000), default=None)

    # Classification
    category = Column(String(200), default="Uncategorized", index=True)
    subcategory = Column(String(200), default=None)
    tags = Column(String(1000), default=None)

    # Content (kept for backward compat; prefer BookContent for new code)
    summary = Column(Text, default=None)
    text_content = Column(Text, default=None)
    page_count = Column(Integer, default=None)

    # Vector search
    vector_id = Column(Integer, default=None)

    # Processing status
    ocr_processed = Column(Boolean, default=False)
    processing_status = Column(String(20), default="pending")
    processing_error = Column(Text, default=None)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        # Composite indexes covering the most common query patterns
        Index("idx_books_category_created", "category", "created_at"),
        Index("idx_books_category_title", "category", "title"),
        Index("idx_books_author", "author"),
        Index("idx_books_format", "format"),
        Index("idx_books_year", "year"),
    )

    def __repr__(self) -> str:
        return f"<Book(id={self.id}, title='{self.title}', author='{self.author}')>"
