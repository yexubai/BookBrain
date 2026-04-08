"""Pydantic schemas for API request/response models.

Defines all data transfer objects (DTOs) used by the REST API:
  - Book schemas (list, detail, update)
  - Category tree schemas
  - Search result schemas (pure semantic + unified keyword/semantic)
  - Ingest pipeline status
  - Settings read/update
  - Library statistics
  - File browser (server-side directory listing)
  - Annotation CRUD schemas
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


# ─── Book Schemas ───────────────────────────────────────────────

class BookBase(BaseModel):
    """Shared book properties used in both responses and updates."""
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
    """Full book response model including file info and timestamps."""
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
    context: Optional[str] = None
    page_number: Optional[int] = None
    location_tag: Optional[str] = None


class SearchResponse(BaseModel):
    """Search response with results."""
    query: str
    results: List[SearchResult]
    total: int


class UnifiedSearchResult(BaseModel):
    """Single result from unified search (keyword + semantic combined).

    The ``source`` field indicates how this result was found:
      - "keyword": FTS5 match on title/author/filename/summary/content
      - "semantic": FAISS vector similarity match by meaning
    """
    book: BookResponse
    score: float = 0.0
    source: str = "keyword"              # "keyword" or "semantic"
    filename: Optional[str] = None       # File stem for display
    context: Optional[str] = None        # Match snippet with <b> highlight tags
    page_number: Optional[int] = None    # Page/chapter where the match was found
    location_tag: Optional[str] = None   # EPUB CFI or PDF page tag for navigation


class UnifiedSearchResponse(BaseModel):
    """Response from the unified search endpoint.

    Includes counts of how many results came from each search engine,
    allowing the frontend to display source distribution badges.
    """
    query: str
    results: List[UnifiedSearchResult]
    total: int
    keyword_count: int = 0      # Number of results from FTS5 keyword search
    semantic_count: int = 0     # Number of results from FAISS semantic search


# ─── Ingest Schemas ─────────────────────────────────────────────

class IngestRequest(BaseModel):
    """Ingest request."""
    directories: Optional[List[str]] = Field(
        default=None,
        description="Specific directories to scan. If empty, uses configured directories."
    )
    force_rescan: bool = False


class IngestStatus(BaseModel):
    """Real-time ingest pipeline status, polled by the frontend."""
    is_running: bool = False
    total_files: int = 0           # Total ebook files discovered
    processed_files: int = 0       # Successfully processed so far
    skipped_files: int = 0         # Already in DB (not force_rescan)
    failed_files: int = 0          # Failed during processing
    current_file: Optional[str] = None  # Filename currently being processed
    errors: List[str] = []         # Error messages for failed files
    progress_percent: float = 0.0  # 0.0 to 100.0


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


# ─── File Browser Schemas ───────────────────────────────────────

class FileBrowserItem(BaseModel):
    """Directory or file item."""
    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None


class FileBrowserResponse(BaseModel):
    """List of files and directories in a path."""
    current_path: str
    parent_path: Optional[str] = None
    items: List[FileBrowserItem]


# ─── Annotation Schemas ─────────────────────────────────────────

class AnnotationBase(BaseModel):
    """Base annotation properties shared between create and response schemas."""
    location: str
    selected_text: str
    note: Optional[str] = ""
    color: Optional[str] = "yellow"

class AnnotationCreate(AnnotationBase):
    """Schema for creating a new annotation."""
    pass

class AnnotationUpdate(BaseModel):
    """Schema for updating an annotation."""
    note: Optional[str] = None
    color: Optional[str] = None

class AnnotationResponse(AnnotationBase):
    """Annotation response model."""
    id: int
    book_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
