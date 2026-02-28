"""CRUD operations for BookBrain database."""

from typing import List, Optional, Tuple

from sqlalchemy import select, func, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Book


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

    Returns tuple of (books, total_count).
    """
    query = select(Book)
    count_query = select(func.count(Book.id))

    # Apply filters
    if category:
        query = query.where(Book.category == category)
        count_query = count_query.where(Book.category == category)

    if format:
        query = query.where(Book.format == format)
        count_query = count_query.where(Book.format == format)

    if search_query:
        like_pattern = f"%{search_query}%"
        search_filter = or_(
            Book.title.ilike(like_pattern),
            Book.author.ilike(like_pattern),
            Book.description.ilike(like_pattern),
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

    # Execute
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
