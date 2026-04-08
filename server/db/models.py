"""SQLAlchemy ORM models for BookBrain.

Defines three tables:
  - ``books``       – core ebook metadata (title, author, file info, classification, etc.)
  - ``chunks``      – page/chapter-level text segments used for deep search and vector embedding
  - ``annotations`` – user highlights and notes attached to specific locations in a book

Additionally, two FTS5 virtual tables (``books_fts``, ``chunks_fts``) are created
in ``database.py`` to enable fast full-text keyword search.
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, Index, ForeignKey
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""
    pass


class Book(Base):
    """Ebook metadata model.

    Each row represents one imported ebook file.  The ``text_content`` column
    stores the full extracted text (up to ``max_text_length`` chars) for FTS5
    indexing.  List queries use ``defer(Book.text_content)`` to avoid loading
    this large column unnecessarily.

    The ``chunks`` relationship provides page-level text segments for
    fine-grained search and vector embedding.
    """

    __tablename__ = "books"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ── Basic bibliographic metadata ───────────────────────────
    title = Column(String(500), nullable=False, index=True)
    author = Column(String(500), default="Unknown")
    isbn = Column(String(20), default=None)
    publisher = Column(String(300), default=None)
    year = Column(Integer, default=None)
    language = Column(String(10), default=None)       # ISO 639-1 code (e.g. "en", "zh")
    description = Column(Text, default=None)

    # ── File information ───────────────────────────────────────
    format = Column(String(10), nullable=False)        # File extension without dot (e.g. "pdf", "epub")
    file_path = Column(String(1000), nullable=False, unique=True)  # Absolute path on disk
    file_size = Column(Integer, default=0)             # Size in bytes
    file_hash = Column(String(64), default=None, index=True)  # SHA-256 hash for deduplication

    # ── Cover image ────────────────────────────────────────────
    cover_path = Column(String(1000), default=None)    # Path to extracted cover image in covers_dir

    # ── Classification ─────────────────────────────────────────
    category = Column(String(200), default="Uncategorized", index=True)  # Top-level category
    subcategory = Column(String(200), default=None)    # Second-level category
    tags = Column(String(1000), default=None)          # Comma-separated tags (reserved for future use)

    # ── Content ────────────────────────────────────────────────
    summary = Column(Text, default=None)               # First ~500 chars of extracted text
    text_content = Column(Text, default=None)           # Full extracted text (deferred in list queries)
    page_count = Column(Integer, default=None)

    # ── Timestamps ─────────────────────────────────────────────
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── Relationships ──────────────────────────────────────────
    chunks = relationship("Chunk", back_populates="book", cascade="all, delete-orphan")

    __table_args__ = (
        # Composite indexes for common query patterns (category filtering + sorting)
        Index("idx_books_category_created", "category", "created_at"),
        Index("idx_books_category_title", "category", "title"),
        Index("idx_books_author", "author"),
        Index("idx_books_format", "format"),
        Index("idx_books_year", "year"),
    )

    def __repr__(self) -> str:
        return f"<Book(id={self.id}, title='{self.title}', author='{self.author}')>"


class Annotation(Base):
    """User highlight and note attached to a specific location in a book.

    The ``location`` field is format-dependent:
      - EPUB: CFI (Canonical Fragment Identifier) string
      - PDF:  JSON-encoded page number + bounding rectangle
    The frontend interprets and renders the location accordingly.
    """

    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)

    location = Column(String(1000), nullable=False)     # Format-specific position identifier
    selected_text = Column(Text, nullable=False)         # The highlighted text passage
    note = Column(Text, default="")                      # Optional user note
    color = Column(String(20), default="yellow")         # Highlight color (hex or named)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    book = relationship("Book", backref="annotations_backref")

    def __repr__(self) -> str:
        return f"<Annotation(id={self.id}, book_id={self.book_id})>"


class Chunk(Base):
    """A segment of text from a book, typically one page or chapter.

    Chunks enable page-level search granularity:
      - ``chunks_fts`` provides FTS5 keyword search on chunk content
      - ``vector_id`` links to the corresponding FAISS vector for semantic search
      - Search results return the chunk's page_number/location_tag so the
        reader can jump directly to the matched location
    """

    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)

    page_number = Column(Integer, default=None)          # 1-based page number (PDF) or sequence index (EPUB)
    location_tag = Column(String(500), default=None)     # EPUB item name or "page_N" tag for PDF
    content = Column(Text, nullable=False)               # The actual text content of this segment
    vector_id = Column(Integer, default=None, index=True)  # Corresponding index in the FAISS vector store

    book = relationship("Book", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<Chunk(id={self.id}, book_id={self.book_id}, page={self.page_number})>"
