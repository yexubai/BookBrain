"""Pydantic schemas for API request/response models."""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


# ─── Book Schemas ───────────────────────────────────────────────

class BookBase(BaseModel):
    """Shared book properties."""
    title: str
    author: str = "Unknown"
    isbn: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    language: Optional[str] = None
    description: Optional[str] = None
    category: str = "Uncategorized"
    subcategory: Optional[str] = None
    tags: Optional[str] = None


class BookResponse(BookBase):
    """Book response model."""
    id: int
    format: str
    file_path: str
    file_size: int = 0
    cover_path: Optional[str] = None
    summary: Optional[str] = None
    page_count: Optional[int] = None
    ocr_processed: bool = False
    processing_status: str = "pending"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BookUpdate(BaseModel):
    """Book update model (all fields optional)."""
    title: Optional[str] = None
    author: Optional[str] = None
    isbn: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    language: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: Optional[str] = None


class BookListResponse(BaseModel):
    """Paginated book list response."""
    books: List[BookResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ─── Category Schemas ───────────────────────────────────────────

class SubcategoryResponse(BaseModel):
    """Subcategory with count."""
    name: str
    count: int


class CategoryResponse(BaseModel):
    """Category with subcategories and counts."""
    name: str
    count: int
    subcategories: List[SubcategoryResponse] = []


# ─── Search Schemas ─────────────────────────────────────────────

class SearchResult(BaseModel):
    """Single search result."""
    book: BookResponse
    score: float = 0.0


class SearchResponse(BaseModel):
    """Search response with results."""
    query: str
    results: List[SearchResult]
    total: int


# ─── Ingest Schemas ─────────────────────────────────────────────

class IngestRequest(BaseModel):
    """Ingest request."""
    directories: Optional[List[str]] = Field(
        default=None,
        description="Specific directories to scan. If empty, uses configured directories."
    )
    force_rescan: bool = False


class IngestStatus(BaseModel):
    """Ingest pipeline status."""
    is_running: bool = False
    total_files: int = 0
    processed_files: int = 0
    failed_files: int = 0
    current_file: Optional[str] = None
    errors: List[str] = []
    progress_percent: float = 0.0


# ─── Settings Schemas ───────────────────────────────────────────

class SettingsResponse(BaseModel):
    """Current settings."""
    ebook_dirs: str = ""
    ocr_enabled: bool = True
    ocr_language: str = "eng+chi_sim"
    embedding_model: str = ""
    max_workers: int = 4
    data_dir: str = ""


class SettingsUpdate(BaseModel):
    """Settings update."""
    ebook_dirs: Optional[str] = None
    ocr_enabled: Optional[bool] = None
    ocr_language: Optional[str] = None
    max_workers: Optional[int] = None


# ─── Stats Schemas ──────────────────────────────────────────────

class StatsResponse(BaseModel):
    """Library statistics."""
    total_books: int = 0
    formats: dict = {}
    category_count: int = 0
    total_size_bytes: int = 0
