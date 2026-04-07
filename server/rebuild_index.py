"""Rebuild FAISS vector index from existing database records."""

import os
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import asyncio
import sqlite3
from search.vector_store import VectorStore
from config import settings


async def main():
    db_path = settings.data_dir / "bookbrain.db"
    print(f"Reading books from: {db_path}")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, author, text_content FROM books")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No books found in database.")
        return

    print(f"Found {len(rows)} books. Building index...")

    texts_and_ids = []
    for book_id, title, author, text_content in rows:
        text = f"{title or ''} {author or ''} {(text_content or '')[:2000]}"
        texts_and_ids.append((text, book_id))

    store = VectorStore()
    await store.rebuild(texts_and_ids)
    print("Done! FAISS index saved to:", settings.index_dir)


if __name__ == "__main__":
    asyncio.run(main())
