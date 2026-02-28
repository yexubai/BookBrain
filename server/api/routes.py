"""REST API routes for BookBrain."""

import math
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.database import get_session
from db.crud import (
    get_books, get_book, create_book, update_book, delete_book,
    get_categories, get_stats, get_book_by_path,
)
from api.schemas import (
    BookResponse, BookListResponse, BookUpdate,
    CategoryResponse, SearchResult, SearchResponse,
    IngestRequest, IngestStatus, SettingsResponse, SettingsUpdate,
    StatsResponse,
)

router = APIRouter(prefix="/api", tags=["api"])


# ─── Books ──────────────────────────────────────────────────────

@router.get("/books", response_model=BookListResponse)
async def list_books(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    format: Optional[str] = None,
    q: Optional[str] = None,
    sort_by: str = Query("created_at", pattern="^(title|author|created_at|file_size|year)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    session: AsyncSession = Depends(get_session),
):
    """List books with pagination and filtering."""
    skip = (page - 1) * page_size
    books, total = await get_books(
        session,
        skip=skip,
        limit=page_size,
        category=category,
        format=format,
        search_query=q,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return BookListResponse(
        books=books,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/books/{book_id}", response_model=BookResponse)
async def get_book_detail(
    book_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get book details by ID."""
    book = await get_book(session, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@router.put("/books/{book_id}", response_model=BookResponse)
async def update_book_detail(
    book_id: int,
    data: BookUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update book metadata."""
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    book = await update_book(session, book_id, **update_data)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@router.delete("/books/{book_id}")
async def delete_book_endpoint(
    book_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete a book record (does not delete the file)."""
    success = await delete_book(session, book_id)
    if not success:
        raise HTTPException(status_code=404, detail="Book not found")
    return {"message": "Book deleted", "id": book_id}


@router.get("/books/{book_id}/cover")
async def get_book_cover(
    book_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get book cover image."""
    book = await get_book(session, book_id)
    if not book or not book.cover_path:
        raise HTTPException(status_code=404, detail="Cover not found")

    cover_path = Path(book.cover_path)
    if not cover_path.exists():
        raise HTTPException(status_code=404, detail="Cover file not found")

    return FileResponse(
        str(cover_path),
        media_type="image/jpeg",
        filename=f"cover_{book_id}.jpg",
    )


# ─── Categories ─────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    session: AsyncSession = Depends(get_session),
):
    """Get category tree with book counts."""
    return await get_categories(session)


# ─── Search ─────────────────────────────────────────────────────

@router.get("/search", response_model=SearchResponse)
async def search_books(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Semantic search across books."""
    # Lazy import to avoid loading ML model until needed
    from search.vector_store import vector_store

    results = await vector_store.search(q, top_k=limit)

    search_results = []
    for vector_id, score in results:
        # Find book by vector_id
        from sqlalchemy import select
        from db.models import Book
        result = await session.execute(
            select(Book).where(Book.vector_id == vector_id)
        )
        book = result.scalar_one_or_none()
        if book:
            search_results.append(SearchResult(book=book, score=float(score)))

    return SearchResponse(
        query=q,
        results=search_results,
        total=len(search_results),
    )


# ─── Ingest ─────────────────────────────────────────────────────

# Global ingest status
_ingest_status = IngestStatus()


def get_ingest_status() -> IngestStatus:
    """Get the global ingest status."""
    return _ingest_status


@router.post("/ingest", response_model=IngestStatus)
async def trigger_ingest(
    request: IngestRequest = None,
    session: AsyncSession = Depends(get_session),
):
    """Trigger ebook directory scan and processing."""
    global _ingest_status

    if _ingest_status.is_running:
        raise HTTPException(status_code=409, detail="Ingest is already running")

    import asyncio
    from ingest.pipeline import IngestPipeline

    # Determine directories to scan
    dirs = []
    if request and request.directories:
        dirs = [Path(d) for d in request.directories]
    else:
        dirs = settings.ebook_directories

    if not dirs:
        raise HTTPException(
            status_code=400,
            detail="No directories configured. Set BOOKBRAIN_EBOOK_DIRS or provide directories in request."
        )

    # Validate directories
    for d in dirs:
        if not d.exists():
            raise HTTPException(status_code=400, detail=f"Directory not found: {d}")

    pipeline = IngestPipeline()
    _ingest_status = IngestStatus(is_running=True)

    # Run pipeline in background
    async def run_pipeline():
        global _ingest_status
        try:
            await pipeline.run(dirs, _ingest_status)
        except Exception as e:
            _ingest_status.errors.append(str(e))
        finally:
            _ingest_status.is_running = False

    asyncio.create_task(run_pipeline())
    return _ingest_status


@router.get("/ingest/status", response_model=IngestStatus)
async def ingest_status():
    """Get current ingest pipeline status."""
    return _ingest_status


# ─── Settings ───────────────────────────────────────────────────

@router.get("/settings", response_model=SettingsResponse)
async def get_settings():
    """Get current settings."""
    return SettingsResponse(
        ebook_dirs=settings.ebook_dirs,
        ocr_enabled=settings.ocr_enabled,
        ocr_language=settings.ocr_language,
        embedding_model=settings.embedding_model,
        max_workers=settings.max_workers,
        data_dir=str(settings.data_dir),
    )


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(data: SettingsUpdate):
    """Update settings (runtime only, does not persist to .env)."""
    if data.ebook_dirs is not None:
        settings.ebook_dirs = data.ebook_dirs
    if data.ocr_enabled is not None:
        settings.ocr_enabled = data.ocr_enabled
    if data.ocr_language is not None:
        settings.ocr_language = data.ocr_language
    if data.max_workers is not None:
        settings.max_workers = data.max_workers

    return SettingsResponse(
        ebook_dirs=settings.ebook_dirs,
        ocr_enabled=settings.ocr_enabled,
        ocr_language=settings.ocr_language,
        embedding_model=settings.embedding_model,
        max_workers=settings.max_workers,
        data_dir=str(settings.data_dir),
    )


# ─── Stats ──────────────────────────────────────────────────────

@router.get("/stats", response_model=StatsResponse)
async def library_stats(
    session: AsyncSession = Depends(get_session),
):
    """Get library statistics."""
    return await get_stats(session)
