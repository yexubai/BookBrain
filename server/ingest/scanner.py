"""Directory scanner for discovering ebook files.

Recursively walks one or more directories and yields paths to files
whose extensions match the configured supported formats (PDF, EPUB,
MOBI, AZW3, TXT, CBZ, HTML).  Uses a generator-based approach to
keep memory usage constant regardless of library size.
"""

import logging
from pathlib import Path
from typing import Generator, List, Set, Tuple

from config import settings

logger = logging.getLogger(__name__)


class Scanner:
    """Recursively scans directories for supported ebook formats.

    Supported formats are read from ``settings.supported_formats`` at
    construction time and stored as a set for O(1) extension lookups.
    """

    def __init__(self):
        self.supported_formats: Set[str] = set(settings.supported_formats)

    def scan_iter(self, directories: List[Path]) -> Generator[Path, None, None]:
        """Yield ebook file paths one by one (memory-efficient streaming).

        Walks each directory recursively using ``rglob("*")`` and filters
        by file extension.  Skips non-existent or non-directory paths with
        a warning.
        """
        for directory in directories:
            if not directory.exists():
                logger.warning("Directory does not exist: %s", directory)
                continue
            if not directory.is_dir():
                logger.warning("Path is not a directory: %s", directory)
                continue
            logger.info("Scanning directory: %s", directory)
            for file_path in directory.rglob("*"):
                if file_path.is_file() and file_path.suffix.lower() in self.supported_formats:
                    yield file_path

    def count(self, directories: List[Path]) -> int:
        """Count ebook files without storing all paths in memory.

        Used before ingest starts to report accurate total for progress tracking.
        """
        return sum(1 for _ in self.scan_iter(directories))

    def scan(self, directories: List[Path]) -> List[Path]:
        """Scan directories and return all matching paths as a list.

        Kept for backward compatibility; prefer ``scan_iter()`` for large libraries.
        """
        found_files = list(self.scan_iter(directories))
        logger.info("Total ebooks found: %d", len(found_files))
        return found_files
