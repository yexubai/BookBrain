"""Multi-threaded ingest pipeline for processing ebooks."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

from config import settings
from db.database import async_session
from db.crud import get_book_by_path, create_book
from ingest.scanner import Scanner
from ingest.extractor import extract_metadata, compute_file_hash
from ingest.ocr import OCRProcessor

logger = logging.getLogger(__name__)


class IngestPipeline:
    """Multi-threaded ebook ingest pipeline.

    Scans directories, extracts metadata/text, runs OCR if needed,
    classifies books, generates embeddings, and stores everything.
    """

    def __init__(self):
        self.scanner = Scanner()
        self.ocr = OCRProcessor()
        self.executor = ThreadPoolExecutor(max_workers=settings.max_workers)

    def _process_single_file(self, file_path: Path) -> dict:
        """Process a single ebook file (runs in thread pool).

        Returns a dict with book data or error info.
        """
        try:
            logger.info("Processing: %s", file_path.name)

            # Extract metadata and text
            metadata = extract_metadata(file_path, settings.max_text_length)

            # File info
            file_hash = compute_file_hash(file_path)
            file_size = file_path.stat().st_size

            # OCR fallback for scanned PDFs
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

            # Save cover image
            cover_path = None
            if metadata.cover_image:
                cover_filename = f"{file_hash}{metadata.cover_ext}"
                cover_file = settings.covers_dir / cover_filename
                cover_file.write_bytes(metadata.cover_image)
                cover_path = str(cover_file)

            # Classify the book
            category = "Uncategorized"
            subcategory = None
            try:
                from classify.classifier import Classifier
                classifier = Classifier()
                cat_result = classifier.classify(
                    title=metadata.title,
                    text=metadata.text_content[:5000],
                    author=metadata.author,
                )
                category = cat_result.get("category", "Uncategorized")
                subcategory = cat_result.get("subcategory")
            except Exception as e:
                logger.warning("Classification failed: %s", e)

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
                    "summary": (metadata.text_content[:500] + "...") if len(metadata.text_content) > 500 else metadata.text_content,
                    "text_content": metadata.text_content,
                    "page_count": metadata.page_count,
                    "ocr_processed": ocr_processed,
                    "processing_status": "done",
                },
            }

        except Exception as e:
            logger.error("Failed to process %s: %s", file_path, e)
            return {
                "success": False,
                "file_path": str(file_path),
                "error": str(e),
            }

    async def run(self, directories: List[Path], status=None) -> None:
        """Run the full ingest pipeline.

        Args:
            directories: Directories to scan.
            status: IngestStatus object to update with progress.
        """
        # Step 1: Scan for files
        files = self.scanner.scan(directories)

        if status:
            status.total_files = len(files)

        if not files:
            logger.info("No ebook files found.")
            return

        logger.info("Starting processing of %d files", len(files))
        loop = asyncio.get_event_loop()

        # Step 2: Process files in thread pool
        for idx, file_path in enumerate(files):
            if status:
                status.current_file = file_path.name
                status.progress_percent = (idx / len(files)) * 100

            # Check if already processed
            async with async_session() as session:
                existing = await get_book_by_path(session, str(file_path))
                if existing:
                    logger.info("Skipping already processed: %s", file_path.name)
                    if status:
                        status.processed_files += 1
                    continue

            # Process in thread pool
            result = await loop.run_in_executor(
                self.executor, self._process_single_file, file_path
            )

            if result["success"]:
                # Save to database
                try:
                    async with async_session() as session:
                        book = await create_book(session, **result["data"])
                        await session.commit()

                        # Generate embedding for vector search
                        try:
                            from search.vector_store import vector_store
                            text_for_embedding = f"{book.title} {book.author} {book.text_content or ''}"
                            vector_id = await vector_store.add_text(
                                text_for_embedding[:2000], book.id
                            )
                            if vector_id is not None:
                                book.vector_id = vector_id
                                await session.commit()
                        except Exception as e:
                            logger.warning("Vector indexing failed for %s: %s", file_path.name, e)

                    if status:
                        status.processed_files += 1
                    logger.info("Saved: %s", result["data"]["title"])
                except Exception as e:
                    logger.error("Failed to save %s: %s", file_path.name, e)
                    if status:
                        status.failed_files += 1
                        status.errors.append(f"{file_path.name}: {e}")
            else:
                if status:
                    status.failed_files += 1
                    status.errors.append(f"{result['file_path']}: {result['error']}")

        if status:
            status.progress_percent = 100.0
            status.current_file = None

        logger.info(
            "Ingest complete: %d processed, %d failed",
            status.processed_files if status else len(files),
            status.failed_files if status else 0,
        )
