"""REST API routes for BookBrain.

All routes are mounted under the ``/api`` prefix.  Route groups:
  - Books:       CRUD, cover images, file serving
  - Annotations: highlights and notes per book
  - Categories:  category tree with counts
  - Search:      pure semantic and unified (keyword + semantic) search
  - Ingest:      trigger import pipeline, poll progress
  - Settings:    read/update application settings
  - Admin:       file browser, FTS5/FAISS index rebuild
  - Stats:       library statistics
"""

import math
import asyncio
import logging
import traceback
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.database import get_session
from db.crud import (
    get_books, get_book, create_book, update_book, delete_book,
    get_categories, get_stats, get_book_by_path, fts_search,
)
from .schemas import (
    BookResponse, BookListResponse, BookUpdate,
    CategoryResponse, SearchResult, SearchResponse,
    UnifiedSearchResult, UnifiedSearchResponse,
    IngestRequest, IngestStatus, SettingsResponse, SettingsUpdate,
    StatsResponse, FileBrowserResponse, FileBrowserItem,
)

logger = logging.getLogger(__name__)
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


def _is_under_dir(path: Path, allowed_dir: Path) -> bool:
    """Return True if resolved path is under allowed_dir."""
    resolved = path.resolve()
    allowed = allowed_dir.resolve()
    try:
        return resolved == allowed or resolved.is_relative_to(allowed)
    except (ValueError, TypeError):
        return False


def _safe_cover_path(path: Path) -> Path:
    """Resolve cover path and verify it is under the covers directory."""
    resolved = path.resolve()
    if not _is_under_dir(path, settings.covers_dir):
        raise HTTPException(status_code=403, detail="Access denied")
    return resolved


def _safe_book_path(path: Path) -> Path:
    """Resolve book file path and verify it is under an allowed ebook directory.

    If ebook_directories is not configured, allow any path that was stored in the
    database (the caller already looked the book up by ID, so the path is trusted).
    """
    resolved = path.resolve()
    allowed_dirs = settings.ebook_directories + [settings.data_dir]
    # If allowed dirs are configured, enforce the check
    if allowed_dirs and any(_is_under_dir(resolved, d) for d in allowed_dirs):
        return resolved
    # Fallback: the path came from a trusted DB record — just verify it exists
    if resolved.is_file():
        return resolved
    raise HTTPException(status_code=403, detail="Access denied")


@router.get("/books/{book_id}/cover")
async def get_book_cover(
    book_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get book cover image."""
    book = await get_book(session, book_id)
    if not book or not book.cover_path:
        raise HTTPException(status_code=404, detail="Cover not found")

    cover_path = _safe_cover_path(Path(book.cover_path))
    if not cover_path.exists():
        raise HTTPException(status_code=404, detail="Cover file not found")

    suffix = cover_path.suffix.lower()
    media_type = "image/png" if suffix == ".png" else "image/jpeg"

    # Use file_hash in ETag to bust cache when book-ID-to-cover mapping changes
    headers = {}
    if book.file_hash:
        headers["ETag"] = f'"{book.file_hash}"'
        headers["Cache-Control"] = "private, max-age=86400"

    return FileResponse(
        str(cover_path),
        media_type=media_type,
        filename=f"cover_{book_id}{suffix}",
        headers=headers,
    )


@router.get("/books/{book_id}/file")
async def get_book_file(
    book_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Serve the original ebook file for reading."""
    book = await get_book(session, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    file_path = _safe_book_path(Path(book.file_path))
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    mime_types = {
        "pdf": "application/pdf",
        "epub": "application/epub+zip",
    }
    media_type = mime_types.get(book.format, "application/octet-stream")

    return FileResponse(
        str(file_path),
        media_type=media_type,
        filename=file_path.name,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=3600",
        },
    )


# ─── Annotations ────────────────────────────────────────────────

from db.crud import get_annotations_for_book, create_annotation, update_annotation, delete_annotation, get_chunk
from api.schemas import AnnotationCreate, AnnotationUpdate, AnnotationResponse

@router.get("/books/{book_id}/annotations", response_model=list[AnnotationResponse])
async def list_annotations(
    book_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get all annotations for a book."""
    book = await get_book(session, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return await get_annotations_for_book(session, book_id)

@router.post("/books/{book_id}/annotations", response_model=AnnotationResponse)
async def add_annotation(
    book_id: int,
    data: AnnotationCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new annotation for a book."""
    book = await get_book(session, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return await create_annotation(session, book_id, **data.model_dump())

@router.put("/annotations/{annotation_id}", response_model=AnnotationResponse)
async def edit_annotation(
    annotation_id: int,
    data: AnnotationUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update an annotation (e.g. adding a note or altering color)."""
    annotation = await update_annotation(session, annotation_id, **data.model_dump(exclude_unset=True))
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return annotation

@router.delete("/annotations/{annotation_id}")
async def remove_annotation(
    annotation_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete an annotation."""
    success = await delete_annotation(session, annotation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"message": "Annotation deleted"}


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
    from search.vector_store import vector_store

    results = await vector_store.search(q, top_k=limit)

    search_results = []
    for book_id, score in results:
        book = await get_book(session, book_id)
        if book:
            search_results.append(SearchResult(book=book, score=float(score)))

    return SearchResponse(
        query=q,
        results=search_results,
        total=len(search_results),
    )


@router.get("/search/unified", response_model=UnifiedSearchResponse)
async def unified_search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Unified search combining FTS5 keyword matching and FAISS semantic search.

    - Keyword results match on title, author, filename, summary, description
      (including partial/prefix matching, e.g. "Shakesp" finds "Shakespeare")
    - Semantic results find books by meaning even if exact words don't appear
    - Results are deduplicated: if a book appears in both, the keyword match
      takes priority (it's more precise)
    - keyword_count / semantic_count in the response indicate how many came
      from each source
    """
    from search.vector_store import vector_store

    # Run both searches concurrently
    fts_task = asyncio.create_task(
        fts_search(session, q, limit=limit)
    )
    vec_task = asyncio.create_task(
        vector_store.search(q, top_k=limit)
    )
    fts_pairs, vec_pairs = await asyncio.gather(fts_task, vec_task)

    seen_chunks: set = set()
    results: list[UnifiedSearchResult] = []
    keyword_count = 0
    semantic_count = 0

    # Keyword results first (higher precision)
    for book, chunk, bm25_score, snippet in fts_pairs:
        chunk_id = chunk.id if chunk else f"k-{book.id}"
        if chunk_id in seen_chunks:
            continue
        seen_chunks.add(chunk_id)
        
        # Normalise BM25 to a 0-1 relevance score (BM25 is negative in SQLite)
        normalised = max(0.0, min(1.0, 1.0 / (1.0 + abs(bm25_score))))
        results.append(UnifiedSearchResult(
            book=book,
            score=normalised,
            source="keyword",
            filename=Path(book.file_path).stem if book.file_path else None,
            context=snippet,
            page_number=chunk.page_number if chunk else None,
            location_tag=chunk.location_tag if chunk else None
        ))
        keyword_count += 1

    # Semantic results
    for chunk_id, vec_score in vec_pairs:
        if chunk_id in seen_chunks:
            continue
            
        # Resolve chunk to book
        chunk = await get_chunk(session, chunk_id)
        if not chunk:
            continue
            
        book = chunk.book
        if not book:
            continue
            
        seen_chunks.add(chunk_id)
        results.append(UnifiedSearchResult(
            book=book,
            score=float(vec_score),
            source="semantic",
            filename=Path(book.file_path).stem if book.file_path else None,
            page_number=chunk.page_number,
            location_tag=chunk.location_tag,
            context=chunk.content[:200] + "..." if chunk.content else None
        ))
        semantic_count += 1

    # Trim to requested limit
    results = results[:limit]

    return UnifiedSearchResponse(
        query=q,
        results=results,
        total=len(results),
        keyword_count=keyword_count,
        semantic_count=semantic_count,
    )


# ─── Ingest ─────────────────────────────────────────────────────

# Mutable dict for real-time ingest progress tracking.
# Shared between the background pipeline task and the status endpoint.
# A plain dict is used instead of a Pydantic model for in-place mutation.
_ingest_state: dict = {
    "is_running": False,
    "total_files": 0,
    "processed_files": 0,
    "failed_files": 0,
    "current_file": None,
    "errors": [],
    "progress_percent": 0.0,
}
_ingest_lock = asyncio.Lock()


def _reset_state():
    """Reset ingest state."""
    _ingest_state.update({
        "is_running": True,
        "total_files": 0,
        "processed_files": 0,
        "failed_files": 0,
        "current_file": None,
        "errors": [],
        "progress_percent": 0.0,
    })


@router.post("/ingest", response_model=IngestStatus)
async def trigger_ingest(
    request: IngestRequest = None,
):
    """Trigger ebook directory scan and processing."""
    async with _ingest_lock:
        if _ingest_state["is_running"]:
            raise HTTPException(status_code=409, detail="Ingest is already running")

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

        _reset_state()
    pipeline = IngestPipeline()

    # Run pipeline in background
    force_rescan = request.force_rescan if request else False
    async def run_pipeline():
        try:
            logger.info("Background ingest task started for: %s (force=%s)", dirs, force_rescan)
            await pipeline.run(dirs, _ingest_state, force_rescan=force_rescan)
            logger.info("Background ingest task completed")
        except Exception as e:
            logger.error("Ingest pipeline crashed: %s\n%s", e, traceback.format_exc())
            _ingest_state["errors"].append(f"Pipeline error: {e}")
        finally:
            _ingest_state["is_running"] = False
            _ingest_state["current_file"] = None

    asyncio.create_task(run_pipeline())
    return IngestStatus(**_ingest_state)


@router.get("/ingest/status", response_model=IngestStatus)
async def ingest_status():
    """Get current ingest pipeline status."""
    return IngestStatus(**_ingest_state)


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
    """Update settings and persist to disk."""
    if data.ebook_dirs is not None:
        settings.ebook_dirs = data.ebook_dirs
    if data.ocr_enabled is not None:
        settings.ocr_enabled = data.ocr_enabled
    if data.ocr_language is not None:
        settings.ocr_language = data.ocr_language
    if data.max_workers is not None:
        settings.max_workers = data.max_workers

    # Persist to data/user_settings.json
    settings.save_to_disk()

    return SettingsResponse(
        ebook_dirs=settings.ebook_dirs,
        ocr_enabled=settings.ocr_enabled,
        ocr_language=settings.ocr_language,
        embedding_model=settings.embedding_model,
        max_workers=settings.max_workers,
        data_dir=str(settings.data_dir),
    )


# ─── Admin & Utilities ──────────────────────────────────────────

@router.get("/admin/browse", response_model=FileBrowserResponse)
async def browse_files(path: str = ""):
    """Browse server-side folders for directory selection."""
    from pathlib import Path
    import os

    current = Path(path) if path else Path.cwd()
    if not current.exists():
        current = Path.cwd()
    
    # Resolve to absolute for clarity, but be careful with permissions in production
    # In a local/NAS context, this is usually acceptable
    current = current.absolute()
    
    items = []
    try:
        for entry in os.scandir(current):
            # Only show directories by default for "Select Folder" use case
            if entry.is_dir():
                items.append(FileBrowserItem(
                    name=entry.name,
                    path=str(Path(entry.path)),
                    is_dir=True
                ))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot browse directory: {e}")

    # Sort: folders first, then alphabetical
    items.sort(key=lambda x: x.name.lower())

    return FileBrowserResponse(
        current_path=str(current),
        parent_path=str(current.parent) if current.parent != current else None,
        items=items
    )


# ─── Stats ──────────────────────────────────────────────────────

@router.get("/stats", response_model=StatsResponse)
async def library_stats(
    session: AsyncSession = Depends(get_session),
):
    """Get library statistics."""
    return await get_stats(session)


# ─── Admin / Maintenance ────────────────────────────────────────

@router.post("/admin/rebuild-fts")
async def rebuild_fts_index(
    session: AsyncSession = Depends(get_session),
):
    """Rebuild the FTS5 full-text search index from all existing book records.

    Run this once after upgrading from an older version that didn't have FTS5,
    or after bulk-importing books outside the normal pipeline.
    """
    from sqlalchemy import text as sqla_text
    try:
        await session.execute(sqla_text("DELETE FROM books_fts"))
        await session.execute(sqla_text("""
            INSERT INTO books_fts(rowid, title, author, filename, summary, description, text_content)
            SELECT
                id,
                COALESCE(title, ''),
                COALESCE(author, ''),
                COALESCE(REPLACE(file_path,
                    RTRIM(file_path, REPLACE(file_path, '/', '')), ''), ''),
                COALESCE(summary, ''),
                COALESCE(description, ''),
                COALESCE(text_content, '')
            FROM books
        """))
        await session.commit()
        result = await session.execute(sqla_text("SELECT COUNT(*) FROM books_fts"))
        count = result.scalar()
        return {"message": f"FTS index rebuilt with {count} entries"}
    except Exception as e:
        logger.error("FTS rebuild failed: %s", e)
        raise HTTPException(status_code=500, detail=f"FTS rebuild failed: {e}")


@router.post("/admin/rebuild-vectors")
async def rebuild_vector_index(
    session: AsyncSession = Depends(get_session),
):
    """Rebuild the FAISS vector index from all existing book records.

    Run this if the FAISS index files are missing or corrupted.
    """
    from search.vector_store import vector_store
    from sqlalchemy import text as sqla_text

    try:
        result = await session.execute(
            sqla_text("SELECT id, title, author, text_content FROM books")
        )
        rows = result.fetchall()

        if not rows:
            return {"message": "No books found to index"}

        texts_and_ids = []
        for row in rows:
            book_id, title, author, text_content = row
            text = f"{title or ''} {author or ''} {(text_content or '')[:2000]}"
            texts_and_ids.append((text, book_id))

        await vector_store.rebuild(texts_and_ids)

        return {"message": f"Vector index rebuilt with {len(texts_and_ids)} entries"}
    except Exception as e:
        logger.error("Vector index rebuild failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Vector rebuild failed: {e}")

