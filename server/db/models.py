"""SQLAlchemy database models for BookBrain."""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, Index
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class Book(Base):
    """Ebook metadata and content model."""

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
    format = Column(String(10), nullable=False)  # pdf, epub
    file_path = Column(String(1000), nullable=False, unique=True)
    file_size = Column(Integer, default=0)  # bytes
    file_hash = Column(String(64), default=None)  # SHA-256

    # Cover
    cover_path = Column(String(1000), default=None)

    # Classification
    category = Column(String(200), default="Uncategorized", index=True)
    subcategory = Column(String(200), default=None)
    tags = Column(String(1000), default=None)  # comma-separated

    # Content
    summary = Column(Text, default=None)
    text_content = Column(Text, default=None)  # First N chars for search
    page_count = Column(Integer, default=None)

    # Vector search
    vector_id = Column(Integer, default=None)  # FAISS vector index ID

    # Processing status
    ocr_processed = Column(Boolean, default=False)
    processing_status = Column(String(20), default="pending")  # pending, processing, done, error
    processing_error = Column(Text, default=None)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes for common queries
    __table_args__ = (
        Index("idx_books_category_title", "category", "title"),
        Index("idx_books_author", "author"),
        Index("idx_books_format", "format"),
    )

    def __repr__(self) -> str:
        return f"<Book(id={self.id}, title='{self.title}', author='{self.author}')>"
