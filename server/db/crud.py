"""CRUD operations and search queries for BookBrain database.

This module contains:
  - FTS5 full-text search with automatic ILIKE fallback for CJK text
  - Standard CRUD for books, chunks, and annotations
  - Paginated book listing with filtering and sorting
  - Category tree aggregation and library statistics
"""

import re
from pathlib import Path
from typing import List, Optional, Tuple

from sqlalchemy import select, func, delete, or_, text
from sqlalchemy.orm import defer, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Book, Chunk


# ─── FTS5 Search Helpers ───────────────────────────────────────

def _build_fts_query(raw: str) -> str:
    """Convert a user query string into a safe FTS5 MATCH expression.

    Strategy:
      1. Strip all FTS5 special characters to prevent syntax errors
      2. Each token becomes a prefix search (``"word"*``) for partial matching
      3. Multi-word queries also try exact phrase matching via OR

    Examples:
      "python"     → ``"python"*``
      "machine learning" → ``"machine learning" OR "machine"* "learning"*``
    """
    # Remove FTS5 operators that could break the query or allow injection
    clean = re.sub(r'[\"\'*^(){}[\]:;,]', ' ', raw).strip()
    tokens = [t for t in clean.split() if t]
    if not tokens:
        return '""'
    # Prefix search for each token (enables partial/prefix matching)
    prefix_terms = " ".join(f'"{t}"*' for t in tokens)
    # Also try exact phrase match for multi-word queries (higher precision)
    if len(tokens) > 1:
        phrase = '"' + " ".join(tokens) + '"'
        return f"{phrase} OR {prefix_terms}"
    return prefix_terms


async def fts_search(
    session: AsyncSession,
    query: str,
    limit: int = 50,
    category: Optional[str] = None,
    format: Optional[str] = None,
) -> List[Tuple[Book, Optional[Chunk], float, str]]:
    """Full-text search using the FTS5 index on chunk content.

    Search cascade (tries each level until results are found):
      1. FTS5 MATCH on chunks_fts → page-level results with BM25 ranking
      2. ILIKE on chunks.content → fallback for CJK text (FTS5 tokenizer limitation)
      3. ILIKE on book metadata (title, author, description, file_path)

    Returns:
        List of (Book, Chunk|None, score, context_snippet) tuples.
        Score is BM25 (negative, lower = better) for FTS5, or -0.5 for ILIKE fallback.
    """
    fts_query = _build_fts_query(query)

    # Build raw SQL for FTS5 search with optional category/format filters
    filters = ""
    params: dict = {"fts_query": fts_query, "limit": limit}
    if category:
        filters += " AND b.category = :category"
        params["category"] = category
    if format:
        filters += " AND b.format = :format"
        params["format"] = format

    sql = text(f"""
        SELECT 
            c.id AS chunk_id,
            b.id AS book_id,
            bm25(chunks_fts) AS score,
            snippet(chunks_fts, 0, '<b>', '</b>', '...', 64) AS context
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.rowid
        JOIN books b ON b.id = c.book_id
        WHERE chunks_fts MATCH :fts_query {filters}
        ORDER BY bm25(chunks_fts)
        LIMIT :limit
    """)

    try:
        result = await session.execute(sql, params)
        rows = result.fetchall()
    except Exception:
        # FTS5 query might fail on certain inputs; fall back to empty
        return []

    if not rows:
        # FTS5 returned no results. This commonly happens with CJK text because
        # the unicode61 tokenizer doesn't segment Chinese characters well.
        # Fall back to ILIKE pattern matching, trying chunks first for page-level results.
        like_pattern = f"%{query}%"

        # Fallback level 2: ILIKE search on chunk content
        chunk_q = (
            select(Chunk)
            .options(joinedload(Chunk.book))
            .where(Chunk.content.ilike(like_pattern))
        )
        if category or format:
            chunk_q = chunk_q.join(Book, Chunk.book_id == Book.id)
            if category:
                chunk_q = chunk_q.where(Book.category == category)
            if format:
                chunk_q = chunk_q.where(Book.format == format)

        chunk_q = chunk_q.order_by(Chunk.book_id, Chunk.page_number).limit(limit)
        chunk_result = await session.execute(chunk_q)
        chunks = list(chunk_result.scalars().unique().all())

        if chunks:
            results = []
            query_lower = query.lower()
            for chunk in chunks:
                if not chunk.book:
                    continue
                content = chunk.content or ""
                idx = content.lower().find(query_lower)
                if idx >= 0:
                    start = max(0, idx - 50)
                    end = min(len(content), idx + len(query) + 50)
                    snippet = content[start:end]
                    # Highlight matched text (case-preserving)
                    match_text = content[idx:idx + len(query)]
                    snippet = snippet.replace(match_text, f"<b>{match_text}</b>", 1)
                    if start > 0:
                        snippet = "..." + snippet
                    if end < len(content):
                        snippet = snippet + "..."
                else:
                    snippet = content[:200] + ("..." if len(content) > 200 else "")
                results.append((chunk.book, chunk, -0.5, snippet))
            return results

        # Fallback level 3: ILIKE search on book-level metadata fields
        filename_pattern = f"%{Path(query).stem}%"
        search_filter = or_(
            Book.title.ilike(like_pattern),
            Book.author.ilike(like_pattern),
            Book.description.ilike(like_pattern),
            Book.file_path.ilike(filename_pattern),
        )

        q = select(Book).options(defer(Book.text_content)).where(search_filter)
        if category:
            q = q.where(Book.category == category)
        if format:
            q = q.where(Book.format == format)

        q = q.limit(limit)
        result = await session.execute(q)
        books = list(result.scalars().all())

        return [(book, None, -0.5, book.summary[:200] if book.summary else "") for book in books]

    # FTS5 matched — resolve chunk_id/book_id pairs to full ORM objects
    results = []
    for row in rows:
        chunk_id, book_id, score, context = row
        # Fetch chunk with its book pre-loaded
        res = await session.execute(
            select(Chunk).options(joinedload(Chunk.book)).where(Chunk.id == chunk_id)
        )
        chunk = res.scalar_one_or_none()
        if chunk and chunk.book:
            results.append((chunk.book, chunk, float(score), context))
    
    return results



# ─── Book CRUD ─────────────────────────────────────────────────

async def create_book(session: AsyncSession, **kwargs) -> Book:
    """Create a new book record and return it with its auto-generated ID."""
    book = Book(**kwargs)
    session.add(book)
    await session.flush()
    await session.refresh(book)
    return book


async def get_book(session: AsyncSession, book_id: int) -> Optional[Book]:
    """Get a book by ID."""
    result = await session.execute(select(Book).where(Book.id == book_id))
    return result.scalar_one_or_none()


async def get_book_by_path(session: AsyncSession, file_path: str) -> Optional[Book]:
    """Get a book by file path."""
    result = await session.execute(
        select(Book).where(Book.file_path == file_path)
    )
    return result.scalar_one_or_none()


async def get_books(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    category: Optional[str] = None,
    format: Optional[str] = None,
    search_query: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> Tuple[List[Book], int]:
    """Get a paginated list of books with optional filters and search.

    When ``search_query`` is provided, delegates to ``fts_search()`` which
    cascades through FTS5 → ILIKE chunk → ILIKE metadata until results are
    found.  Without a search query, returns a standard paginated listing.

    Args:
        skip: Number of records to skip (for pagination).
        limit: Maximum number of records to return.
        category: Filter by category name (exact match).
        format: Filter by file format (e.g. "pdf", "epub").
        search_query: Full-text search query string.
        sort_by: Column to sort by (title, author, created_at, file_size, year).
        sort_order: "asc" or "desc".

    Returns:
        Tuple of (list of Book objects, total count).
    """
    # Defer the large text_content column — list views never need the full text
    query = select(Book).options(defer(Book.text_content))
    count_query = select(func.count(Book.id))

    # Apply filters
    if category:
        query = query.where(Book.category == category)
        count_query = count_query.where(Book.category == category)

    if format:
        query = query.where(Book.format == format)
        count_query = count_query.where(Book.format == format)

    if search_query:
        # Delegate to fts_search() which handles the FTS5 → ILIKE cascade.
        # Request enough results to cover the requested page after deduplication.
        fts_results = await fts_search(
            session, search_query, limit=skip + limit,
            category=category, format=format
        )
        if fts_results:
            # fts_search returns (Book, Chunk, score, snippet) tuples with
            # possible duplicate books (same book matched on multiple chunks).
            # Deduplicate by book ID before paginating.
            seen = set()
            books = []
            for b, _chunk, _score, _snippet in fts_results:
                if b.id not in seen:
                    seen.add(b.id)
                    books.append(b)
            total = len(books)
            return books[skip:skip + limit], total
        else:
            return [], 0
            
    # Sort
    sort_column = getattr(Book, sort_by, Book.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # Pagination
    query = query.offset(skip).limit(limit)

    total_result = await session.execute(count_query)
    total = total_result.scalar()

    result = await session.execute(query)
    books = list(result.scalars().all())

    return books, total


async def update_book(
    session: AsyncSession, book_id: int, **kwargs
) -> Optional[Book]:
    """Update a book by ID."""
    book = await get_book(session, book_id)
    if not book:
        return None

    for key, value in kwargs.items():
        if hasattr(book, key):
            setattr(book, key, value)

    await session.flush()
    await session.refresh(book)
    return book


async def delete_book(session: AsyncSession, book_id: int) -> bool:
    """Delete a book by ID."""
    result = await session.execute(delete(Book).where(Book.id == book_id))
    return result.rowcount > 0



# ─── Category & Stats Queries ──────────────────────────────────

async def get_categories(session: AsyncSession) -> List[dict]:
    """Build a category tree with book counts.

    Returns a list of top-level categories, each containing its total
    book count and a list of subcategories with their individual counts.
    """
    result = await session.execute(
        select(
            Book.category,
            Book.subcategory,
            func.count(Book.id).label("count"),
        )
        .group_by(Book.category, Book.subcategory)
        .order_by(Book.category, Book.subcategory)
    )

    categories = {}
    for row in result.all():
        cat = row.category or "Uncategorized"
        subcat = row.subcategory
        count = row.count

        if cat not in categories:
            categories[cat] = {"name": cat, "count": 0, "subcategories": []}

        categories[cat]["count"] += count
        if subcat:
            categories[cat]["subcategories"].append({
                "name": subcat,
                "count": count,
            })

    return list(categories.values())


async def get_stats(session: AsyncSession) -> dict:
    """Get library statistics."""
    total_result = await session.execute(select(func.count(Book.id)))
    total = total_result.scalar()

    format_result = await session.execute(
        select(Book.format, func.count(Book.id))
        .group_by(Book.format)
    )
    formats = {row[0]: row[1] for row in format_result.all()}

    cat_result = await session.execute(
        select(func.count(func.distinct(Book.category)))
    )
    category_count = cat_result.scalar()

    size_result = await session.execute(select(func.sum(Book.file_size)))
    total_size = size_result.scalar() or 0

    return {
        "total_books": total,
        "formats": formats,
        "category_count": category_count,
        "total_size_bytes": total_size,
    }


# ─── Annotation CRUD ───────────────────────────────────────────

from db.models import Annotation

async def get_annotations_for_book(session: AsyncSession, book_id: int) -> List[Annotation]:
    """Get all annotations for a specific book, ordered by creation time."""
    result = await session.execute(
        select(Annotation)
        .where(Annotation.book_id == book_id)
        .order_by(Annotation.created_at.asc())
    )
    return list(result.scalars().all())

async def create_annotation(session: AsyncSession, book_id: int, **kwargs) -> Annotation:
    """Create a new annotation for a book."""
    annotation = Annotation(book_id=book_id, **kwargs)
    session.add(annotation)
    await session.commit()
    await session.refresh(annotation)
    return annotation

async def update_annotation(session: AsyncSession, annotation_id: int, **kwargs) -> Optional[Annotation]:
    """Update an existing annotation."""
    result = await session.execute(select(Annotation).where(Annotation.id == annotation_id))
    annotation = result.scalar_one_or_none()
    if not annotation:
        return None
        
    for key, value in kwargs.items():
        if hasattr(annotation, key) and value is not None:
            setattr(annotation, key, value)
            
    await session.commit()
    await session.refresh(annotation)
    return annotation

async def delete_annotation(session: AsyncSession, annotation_id: int) -> bool:
    """Delete an annotation by ID."""
    result = await session.execute(delete(Annotation).where(Annotation.id == annotation_id))
    await session.commit()
    return result.rowcount > 0


# ─── Chunk CRUD ────────────────────────────────────────────────

async def create_chunks(session: AsyncSession, book_id: int, chunks_data: List[dict]) -> None:
    """Bulk-create text chunks for a book from a list of dicts.

    Each dict should contain: content, page_number (optional), location_tag (optional).
    The chunks_fts trigger will automatically index the content for FTS5 search.
    """
    chunks = [Chunk(book_id=book_id, **data) for data in chunks_data]
    session.add_all(chunks)
    await session.flush()

async def get_chunk(session: AsyncSession, chunk_id: int) -> Optional[Chunk]:
    """Get a chunk by ID with its book relationship pre-loaded."""
    result = await session.execute(
        select(Chunk).options(joinedload(Chunk.book)).where(Chunk.id == chunk_id)
    )
    return result.scalar_one_or_none()

async def get_chunk_by_vector_id(session: AsyncSession, vector_id: int) -> Optional[Chunk]:
    """Get a chunk by its vector database ID with its book relationship pre-loaded."""
    result = await session.execute(
        select(Chunk).options(joinedload(Chunk.book)).where(Chunk.vector_id == vector_id)
    )
    return result.scalar_one_or_none()

async def get_chunks_for_book(session: AsyncSession, book_id: int) -> List[Chunk]:
    """Get all chunks for a specific book."""
    result = await session.execute(
        select(Chunk)
        .where(Chunk.book_id == book_id)
        .order_by(Chunk.page_number.asc(), Chunk.id.asc())
    )
    return list(result.scalars().all())

async def update_chunk(session: AsyncSession, chunk_id: int, **kwargs) -> Optional[Chunk]:
    """Update a chunk record."""
    chunk = await get_chunk(session, chunk_id)
    if not chunk:
        return None
    for key, value in kwargs.items():
        if hasattr(chunk, key):
            setattr(chunk, key, value)
    await session.flush()
    return chunk
