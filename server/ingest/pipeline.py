"""Multi-threaded ingest pipeline for processing ebooks.

Orchestrates the full import workflow:
  1. Scan directories for ebook files (Scanner)
  2. Skip files already in the database (unless force_rescan)
  3. Extract metadata and text in a thread pool (Extractor + OCR)
  4. Classify each book (rule-based then ML zero-shot)
  5. Batch-commit books and chunks to the database
  6. Generate vector embeddings for all chunks (sentence-transformers + FAISS)
  7. Persist the FAISS index to disk

The pipeline runs asynchronously in the background and reports progress
through a shared ``status`` dict that the API polls via ``/api/ingest/status``.
"""

import asyncio
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from config import settings
from db.database import async_session
from db.crud import get_book_by_path, create_book, create_chunks, update_chunk, get_chunks_for_book
from ingest.scanner import Scanner
from ingest.extractor import extract_metadata, compute_file_hash
from ingest.ocr import OCRProcessor

logger = logging.getLogger(__name__)

_CONCURRENCY = settings.max_workers  # Number of concurrent file-processing workers


class IngestPipeline:
    """Multi-threaded ebook ingest pipeline.

    Scans directories, extracts metadata/text, runs OCR if needed,
    classifies books, generates embeddings, and stores everything.

    Key design decisions:
      - CPU-bound extraction runs in a ThreadPoolExecutor to avoid blocking the event loop
      - Books are batched (``db_batch_size``) before DB commit to reduce transaction overhead
      - Vector embeddings are generated after DB commit to isolate FAISS errors from data storage
      - An asyncio.Queue with bounded size (workers * 2) provides backpressure
    """

    def __init__(self):
        self.scanner = Scanner()
        self.ocr = OCRProcessor()
        self.executor = ThreadPoolExecutor(max_workers=settings.max_workers)
        self._classifier = None

    def _get_classifier(self):
        if self._classifier is None:
            try:
                from classify.classifier import Classifier
                self._classifier = Classifier()
            except Exception as e:
                logger.warning("Could not initialize classifier: %s", e)
        return self._classifier

    def _process_single_file(self, file_path: Path) -> dict:
        """Process a single ebook file (runs in thread pool)."""
        try:
            logger.info("Processing: %s", file_path.name)

            metadata = extract_metadata(file_path, settings.max_text_length)
            file_hash = compute_file_hash(file_path)
            file_size = file_path.stat().st_size

            ocr_processed = False
            if (
                file_path.suffix.lower() == ".pdf"
                and metadata.page_count
                and self.ocr.is_scanned_pdf(file_path, metadata.text_content, metadata.page_count)
            ):
                ocr_text = self.ocr.process_pdf(file_path, settings.max_text_length)
                if ocr_text:
                    metadata.text_content = ocr_text
                    ocr_processed = True

            cover_path = None
            if metadata.cover_image:
                try:
                    cover_filename = f"{file_hash}{metadata.cover_ext}"
                    cover_file = settings.covers_dir / cover_filename
                    cover_file.write_bytes(metadata.cover_image)
                    cover_path = str(cover_file)
                except Exception as e:
                    logger.warning("Failed to save cover for %s: %s", file_path.name, e)

            category = "Uncategorized"
            subcategory = None
            try:
                classifier = self._get_classifier()
                if classifier:
                    cat_result = classifier.classify(
                        title=metadata.title,
                        text=metadata.text_content[:5000],
                        author=metadata.author,
                    )
                    category = cat_result.get("category", "Uncategorized")
                    subcategory = cat_result.get("subcategory")
            except Exception as e:
                logger.warning("Classification failed for %s: %s", file_path.name, e)

            summary = ""
            if metadata.text_content:
                summary = metadata.text_content[:500]
                if len(metadata.text_content) > 500:
                    summary += "..."

            return {
                "success": True,
                "data": {
                    "title": metadata.title or file_path.stem,
                    "author": metadata.author,
                    "isbn": metadata.isbn,
                    "publisher": metadata.publisher,
                    "year": metadata.year,
                    "language": metadata.language,
                    "description": metadata.description,
                    "format": file_path.suffix.lstrip(".").lower(),
                    "file_path": str(file_path),
                    "file_size": file_size,
                    "file_hash": file_hash,
                    "cover_path": cover_path,
                    "category": category,
                    "subcategory": subcategory,
                    "summary": summary,
                    "text_content": metadata.text_content,
                    "chunks": metadata.chunks,
                    "page_count": metadata.page_count,
                    "ocr_processed": ocr_processed,
                    "processing_status": "done",
                },
            }

        except Exception as e:
            logger.error("Failed to process %s: %s\n%s", file_path, e, traceback.format_exc())
            return {
                "success": False,
                "file_path": str(file_path),
                "error": str(e),
            }

    async def _flush_batch(self, batch: list) -> tuple[int, int]:
        """Commit a batch of processed books to the database.

        For each result in the batch:
          - If the book already exists (force_rescan), update it and re-chunk
          - Otherwise, create a new book record and its chunks

        After the DB commit succeeds, vector embeddings are generated for
        all chunks in a separate try/except so FAISS errors don't roll back
        the stored data.

        Returns:
            Tuple of (successfully_saved_count, failed_count).
        """
        if not batch:
            return 0, 0
        saved = 0
        failed = 0
        try:
            async with async_session() as session:
                books_to_embed = []
                for result in batch:
                    if result["success"]:
                        try:
                            # Handle force_rescan / duplicates
                            existing = await get_book_by_path(session, result["data"]["file_path"])
                            if existing:
                                # Update existing book
                                from db.crud import update_book
                                data = result["data"]
                                book = await update_book(session, existing.id, **{k: v for k, v in data.items() if k != "chunks"})
                            else:
                                # Create new book
                                book = await create_book(session, **{k: v for k, v in result["data"].items() if k != "chunks"})
                            
                            # Save chunks (even for existing books, we re-chunk on rescan)
                            if "chunks" in result["data"]:
                                # Delete old chunks first if updating
                                if existing:
                                    from sqlalchemy import delete
                                    from db.models import Chunk
                                    await session.execute(delete(Chunk).where(Chunk.book_id == existing.id))
                                
                                await create_chunks(session, book.id, result["data"]["chunks"])
                            
                            books_to_embed.append(book)
                            saved += 1
                        except Exception as e:
                            logger.error("Failed to store book/chunks: %s", e)
                            failed += 1
                    else:
                        failed += 1
                await session.commit()
        except Exception as e:
            logger.error("Batch DB commit failed: %s\n%s", e, traceback.format_exc())
            # Count all as failed if whole batch fails
            failed = len(batch)
            saved = 0
            return saved, failed

        # Batch vector embedding outside the DB session.
        # Wrapped in its own try-except to prevent vector errors from rolling back the main DB storage.
        try:
            await self._embed_books(books_to_embed)
        except Exception as e:
            logger.warning("Vector indexing delayed for batch: %s. Books were saved, but may not be searchable semantically until next heal.", e)

        return saved, failed

    async def _embed_books(self, books: list) -> None:
        """Generate and store vector embeddings for all chunks of the given books.

        Each chunk's text is prepended with the book's title and author to
        provide context, improving semantic search relevance.  The resulting
        vector IDs are written back to the Chunk.vector_id column.
        """
        if not books:
            return
        try:
            from search.vector_store import vector_store
            
            async with async_session() as session:
                all_texts = []
                all_chunk_ids = []
                
                for book in books:
                    try:
                        chunks = await get_chunks_for_book(session, book.id)
                        for chunk in chunks:
                            # Contextualize chunk with title/author for better semantic matching
                            contextual_text = f"{book.title} {book.author} {chunk.content}"
                            all_texts.append(contextual_text)
                            all_chunk_ids.append(chunk.id)
                    except Exception as e:
                         logger.warning("Failed to collect chunks for book %s (ID: %d): %s", book.title, book.id, e)
                
                if not all_texts:
                    return

                logger.info("Generating embeddings for %d chunks", len(all_texts))
                try:
                    vector_ids = await vector_store.add_texts(all_texts, all_chunk_ids)

                    # Update vector_ids in Chunk table
                    for chunk_id, vid in zip(all_chunk_ids, vector_ids):
                        if vid is not None:
                            await update_chunk(session, chunk_id, vector_id=vid)
                except Exception as e:
                    logger.error("FAISS index update failed in batch: %s", e)
                
                await session.commit()
        except Exception as e:
            logger.warning("Batch vector indexing process hit a high-level error: %s\n%s", e, traceback.format_exc())

    async def run(self, directories: List[Path], status: dict = None, force_rescan: bool = False) -> None:
        """Run the full ingest pipeline with parallel file processing.

        Args:
            directories: List of directory paths to scan for ebook files.
            status: Mutable dict for real-time progress reporting (polled by the API).
            force_rescan: If True, re-process files that are already in the database.
        """
        loop = asyncio.get_running_loop()
        counter_lock = asyncio.Lock()
        batch: list = []
        batch_lock = asyncio.Lock()

        # Count files first for accurate progress reporting (fast OS-level scan)
        logger.info("Counting files in: %s", directories)
        total = await loop.run_in_executor(self.executor, self.scanner.count, directories)
        logger.info("Total files to process: %d", total)
        if status is not None:
            status["total_files"] = total

        if total == 0:
            logger.info("No ebook files found.")
            return

        processed_count = 0
        skipped_count = 0
        failed_count = 0
        
        # Memory-efficient task processing using a queue
        queue: asyncio.Queue = asyncio.Queue(maxsize=settings.max_workers * 2)

        async def worker():
            nonlocal processed_count, skipped_count, failed_count, batch
            while True:
                file_path = await queue.get()
                if file_path is None:
                    queue.task_done()
                    break
                
                try:
                    # 1. Skip already-processed files unless force_rescan is True
                    async with async_session() as session:
                        existing = await get_book_by_path(session, str(file_path))
                        if existing and not force_rescan:
                            async with counter_lock:
                                skipped_count += 1
                                if status is not None:
                                    status["skipped_files"] = skipped_count
                                    status["progress_percent"] = (processed_count + skipped_count + failed_count) / total * 100
                            queue.task_done()
                            continue
                    
                    if status is not None:
                        status["current_file"] = file_path.name
                    
                    # 2. Process file in thread pool
                    result = await loop.run_in_executor(
                        self.executor, self._process_single_file, file_path
                    )
                    
                    # 3. Accumulate into batch
                    flush_now = False
                    async with batch_lock:
                        batch.append(result)
                        if len(batch) >= settings.db_batch_size:
                            current_batch, batch = batch, []
                            flush_now = True
                    
                    if flush_now:
                        saved, failed = await self._flush_batch(current_batch)
                        async with counter_lock:
                            processed_count += saved
                            failed_count += failed
                except Exception as e:
                    logger.error("Worker error for %s: %s", file_path.name, e)
                    async with counter_lock:
                        failed_count += 1
                        if status is not None:
                            status["errors"].append(f"{file_path}: {e}")
                finally:
                    if status is not None:
                        status["processed_files"] = processed_count
                        status["skipped_files"] = skipped_count
                        status["failed_files"] = failed_count
                        status["progress_percent"] = (processed_count + skipped_count + failed_count) / total * 100
                    queue.task_done()

        # Start workers
        worker_tasks = [asyncio.create_task(worker()) for _ in range(settings.max_workers)]

        # Stream files into queue
        for fp in self.scanner.scan_iter(directories):
            await queue.put(fp)
            
        # Signal workers to exit
        for _ in range(settings.max_workers):
            await queue.put(None)
            
        await asyncio.gather(*worker_tasks)

        # Flush remaining batch
        async with batch_lock:
            remaining, batch = batch, []
        if remaining:
            saved, failed = await self._flush_batch(remaining)
            processed_count += saved
            failed_count += failed

        # Persist FAISS index to disk so it survives server restarts
        try:
            from search.vector_store import vector_store
            await vector_store.save()
        except Exception as e:
            logger.warning("Failed to save vector index: %s", e)

        if status is not None:
            status["progress_percent"] = 100.0
            status["processed_files"] = processed_count
            status["failed_files"] = failed_count
            status["current_file"] = None

        logger.info("Ingest complete: %d processed, %d failed", processed_count, failed_count)
