"""CRUD operations for BookBrain database."""

import re
from pathlib import Path
from typing import List, Optional, Tuple

from sqlalchemy import select, func, delete, or_, text
from sqlalchemy.orm import defer
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Book


def _build_fts_query(raw: str) -> str:
    """Convert a user query string into a safe FTS5 MATCH expression.

    Strategy:
      - Each token is searched as a prefix (word*) for partial matching
      - The whole phrase is also searched verbatim for phrase matching
      - Special FTS5 characters are escaped to avoid syntax errors
    """
    # Strip FTS5 special operators so user input can't break the query
    clean = re.sub(r'[\"\'*^(){}[\]:;,]', ' ', raw).strip()
    tokens = [t for t in clean.split() if t]
    if not tokens:
        return '""'
    # Prefix search for each token (partial/fuzzy match)
    prefix_terms = " ".join(f'"{t}"*' for t in tokens)
    # Also try exact phrase if multi-word
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
) -> List[Tuple[Book, float]]:
    """Full-text search using the FTS5 index. Returns (book, bm25_score) pairs.

    Searches title, author, filename, summary, and description.
    Results are ranked by BM25 relevance (lower = better in SQLite FTS5).
    """
    fts_query = _build_fts_query(query)

    # Build the raw SQL; category/format filters are applied as JOINed WHERE clauses
    filters = ""
    params: dict = {"fts_query": fts_query, "limit": limit}
    if category:
        filters += " AND b.category = :category"
        params["category"] = category
    if format:
        filters += " AND b.format = :format"
        params["format"] = format

    sql = text(f"""
        SELECT b.id, bm25(books_fts) AS score
        FROM books_fts
        JOIN books b ON b.id = books_fts.rowid
        WHERE books_fts MATCH :fts_query {filters}
        ORDER BY bm25(books_fts)
        LIMIT :limit
    """)

    try:
        result = await session.execute(sql, params)
        rows = result.fetchall()
    except Exception:
        # FTS5 query might fail on certain inputs; fall back to empty
        return []

    if not rows:
        return []

    # Fetch full Book objects for the matched IDs
    book_ids = [row[0] for row in rows]
    score_map = {row[0]: row[1] for row in rows}

    books_result = await session.execute(
        select(Book).options(defer(Book.text_content)).where(Book.id.in_(book_ids))
    )
    books_by_id = {b.id: b for b in books_result.scalars().all()}

    # Return in relevance order (BM25 ascending = more relevant first)
    return [
        (books_by_id[bid], score_map[bid])
        for bid in book_ids
        if bid in books_by_id
    ]


async def create_book(session: AsyncSession, **kwargs) -> Book:
    """Create a new book record."""
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
    """Get paginated list of books with optional filters.

    When search_query is provided, uses FTS5 for fast full-text matching
    (title, author, filename, summary, description). Falls back to ILIKE
    if FTS5 returns no results.

    Returns tuple of (books, total_count).
    """
    # Defer large text column — list views don't need full content
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
        # Try FTS5 first — fast and searches filename too
        fts_results = await fts_search(
            session, search_query, limit=skip + limit,
            category=category, format=format
        )
        if fts_results:
            books = [b for b, _ in fts_results]
            total = len(fts_results)
            return books[skip:skip + limit], total

        # FTS5 returned nothing — fall back to ILIKE for backward compat
        like_pattern = f"%{search_query}%"
        filename_pattern = f"%{Path(search_query).stem}%"
        search_filter = or_(
            Book.title.ilike(like_pattern),
            Book.author.ilike(like_pattern),
            Book.description.ilike(like_pattern),
            Book.file_path.ilike(filename_pattern),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

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


async def get_categories(session: AsyncSession) -> List[dict]:
    """Get category tree with book counts."""
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
