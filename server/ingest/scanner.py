"""Directory scanner for finding ebook files."""

import logging
from pathlib import Path
from typing import List, Set

from config import settings

logger = logging.getLogger(__name__)


class Scanner:
    """Recursively scans directories for supported ebook formats."""

    def __init__(self):
        self.supported_formats: Set[str] = set(settings.supported_formats)

    def scan(self, directories: List[Path]) -> List[Path]:
        """Scan directories for ebook files.

        Args:
            directories: List of directories to scan.

        Returns:
            List of found ebook file paths.
        """
        found_files = []

        for directory in directories:
            if not directory.exists():
                logger.warning("Directory does not exist: %s", directory)
                continue

            if not directory.is_dir():
                logger.warning("Path is not a directory: %s", directory)
                continue

            logger.info("Scanning directory: %s", directory)
            count = 0

            for file_path in directory.rglob("*"):
                if file_path.is_file() and file_path.suffix.lower() in self.supported_formats:
                    found_files.append(file_path)
                    count += 1

            logger.info("Found %d ebook(s) in %s", count, directory)

        logger.info("Total ebooks found: %d", len(found_files))
        return found_files
