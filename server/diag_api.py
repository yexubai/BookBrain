import asyncio
import os
import sys

# Add server directory to path
sys.path.append(r"d:\code\BookBrain\server")

from db.database import async_session, engine
from db.crud import get_categories, get_books

async def main():
    async with async_session() as session:
        cats = await get_categories(session)
        print("--- Categories ---")
        for cat in cats:
            print(f"Name: {cat.get('name')}, Count: {cat.get('count')}")
        
        books, total = await get_books(session, skip=0, limit=20)
        print(f"\n--- Total Books from get_books: {total} ---")
        for book in books:
            print(f"ID: {book.id} | Category: {book.category} | Title: {book.title[:40]}")

if __name__ == "__main__":
    asyncio.run(main())
