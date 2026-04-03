"""Directory scanner for finding ebook files."""

import logging
from pathlib import Path
from typing import Generator, List, Set, Tuple

from config import settings

logger = logging.getLogger(__name__)


class Scanner:
    """Recursively scans directories for supported ebook formats."""

    def __init__(self):
        self.supported_formats: Set[str] = set(settings.supported_formats)

    def scan_iter(self, directories: List[Path]) -> Generator[Path, None, None]:
        """Yield ebook file paths one by one without loading all into memory."""
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
        """Count ebook files without storing paths."""
        return sum(1 for _ in self.scan_iter(directories))

    def scan(self, directories: List[Path]) -> List[Path]:
        """Scan directories for ebook files (kept for compatibility)."""
        found_files = list(self.scan_iter(directories))
        logger.info("Total ebooks found: %d", len(found_files))
        return found_files
