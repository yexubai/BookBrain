"""Multi-threaded ingest pipeline for processing ebooks."""

import asyncio
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from config import settings
from db.database import async_session
from db.crud import get_book_by_path, create_book
from ingest.scanner import Scanner
from ingest.extractor import extract_metadata, compute_file_hash
from ingest.ocr import OCRProcessor

logger = logging.getLogger(__name__)

# How many files to process concurrently
_CONCURRENCY = settings.max_workers


class IngestPipeline:
    """Multi-threaded ebook ingest pipeline.

    Scans directories, extracts metadata/text, runs OCR if needed,
    classifies books, generates embeddings, and stores everything.
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
        """Commit a batch of processed books to DB. Returns (saved, failed)."""
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
                            book = await create_book(session, **result["data"])
                            books_to_embed.append(book)
                            saved += 1
                        except Exception as e:
                            logger.error("Failed to create book record: %s", e)
                            failed += 1
                    else:
                        failed += 1
                await session.commit()
        except Exception as e:
            logger.error("Batch DB commit failed: %s", e)
            # Count all as failed if whole batch fails
            failed = len(batch)
            saved = 0
            return saved, failed

        # Batch vector embedding outside the DB session
        await self._embed_books(books_to_embed)

        return saved, failed

    async def _embed_books(self, books: list) -> None:
        """Generate and store embeddings for a list of book objects."""
        if not books:
            return
        try:
            from search.vector_store import vector_store
            texts = [
                f"{b.title} {b.author} {b.text_content[:2000] if b.text_content else ''}"
                for b in books
            ]
            ids = [b.id for b in books]
            vector_ids = await vector_store.add_texts(texts, ids)

            # Update vector_ids in DB
            updates = [(b.id, vid) for b, vid in zip(books, vector_ids) if vid is not None]
            if updates:
                async with async_session() as session:
                    from db.crud import update_book
                    for book_id, vid in updates:
                        await update_book(session, book_id, vector_id=vid)
                    await session.commit()
        except Exception as e:
            logger.warning("Batch vector indexing failed: %s", e)

    async def run(self, directories: List[Path], status: dict = None) -> None:
        """Run the full ingest pipeline with parallel file processing."""
        loop = asyncio.get_running_loop()
        semaphore = asyncio.Semaphore(_CONCURRENCY)
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
        failed_count = 0

        async def process_one(file_path: Path) -> None:
            nonlocal processed_count, failed_count, batch

            # Skip already-processed files
            try:
                async with async_session() as session:
                    existing = await get_book_by_path(session, str(file_path))
                    if existing:
                        logger.debug("Skipping already processed: %s", file_path.name)
                        async with counter_lock:
                            processed_count += 1
                            if status is not None:
                                status["processed_files"] = processed_count
                                status["progress_percent"] = (processed_count + failed_count) / total * 100
                        return
            except Exception as e:
                logger.error("DB check failed for %s: %s", file_path.name, e)

            if status is not None:
                status["current_file"] = file_path.name

            async with semaphore:
                try:
                    result = await loop.run_in_executor(
                        self.executor, self._process_single_file, file_path
                    )
                except Exception as e:
                    logger.error("Thread pool error for %s: %s", file_path.name, e)
                    result = {"success": False, "file_path": str(file_path), "error": str(e)}

            # Accumulate into batch
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
                    if status is not None:
                        status["processed_files"] = processed_count
                        status["failed_files"] = failed_count
                        status["progress_percent"] = (processed_count + failed_count) / total * 100
                        if result.get("error"):
                            status["errors"].append(f"{result['file_path']}: {result['error']}")
            else:
                if not result["success"] and status is not None:
                    status["errors"].append(f"{result['file_path']}: {result['error']}")

        # Launch all tasks; semaphore limits actual concurrency
        tasks = [process_one(fp) for fp in self.scanner.scan_iter(directories)]
        await asyncio.gather(*tasks)

        # Flush remaining batch
        async with batch_lock:
            remaining, batch = batch, []
        if remaining:
            saved, failed = await self._flush_batch(remaining)
            processed_count += saved
            failed_count += failed

        if status is not None:
            status["progress_percent"] = 100.0
            status["processed_files"] = processed_count
            status["failed_files"] = failed_count
            status["current_file"] = None

        logger.info("Ingest complete: %d processed, %d failed", processed_count, failed_count)
