"""BookBrain configuration management.

Centralises all application settings using pydantic-settings.  Values are
resolved in this order (highest priority first):
  1. Environment variables with the ``BOOKBRAIN_`` prefix
  2. A ``.env`` file in the working directory
  3. Persisted user settings in ``data/user_settings.json``
  4. Hardcoded defaults below
"""

import os
from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings with environment variable support.

    All fields can be overridden via ``BOOKBRAIN_<FIELD>`` env vars.
    """

    # ── Application identity ───────────────────────────────────
    app_name: str = "BookBrain"
    app_version: str = "0.1.0"
    debug: bool = False  # Enables verbose logging and SQL echo

    # ── Server binding ─────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    # ── Database ───────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/bookbrain.db",
        description="SQLAlchemy async database URL",
    )

    # ── Ebook directories ──────────────────────────────────────
    # Comma-separated list of absolute paths to scan for ebooks.
    ebook_dirs: str = Field(
        default="",
        description="Comma-separated list of directories to scan for ebooks",
    )

    # ── File storage paths ─────────────────────────────────────
    data_dir: Path = Field(default=Path("./data"), description="Root data directory")
    covers_dir: Path = Field(default=Path("./data/covers"), description="Extracted cover images")
    index_dir: Path = Field(default=Path("./data/index"), description="FAISS index files")

    # ── OCR settings ───────────────────────────────────────────
    ocr_enabled: bool = True
    ocr_language: str = "ch_sim+en"  # EasyOCR language codes ('+' separated)
    ocr_max_pages: int = 20  # Max pages to OCR per PDF (performance guard)
    scanned_text_threshold: float = 0.1  # Chars-per-page ratio below which a PDF is deemed scanned

    # ── ML / Embedding model ───────────────────────────────────
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"  # sentence-transformers model name
    embedding_dimension: int = 384  # Must match the chosen model's output dimension

    # ── Processing tuning ──────────────────────────────────────
    max_workers: int = Field(
        default=max(1, (os.cpu_count() or 4) // 2),
        description="Concurrent processing threads (defaults to half of logical CPU cores)",
    )
    max_text_length: int = 2000000  # Max characters of text to store per book
    batch_size: int = 32            # Number of texts per embedding batch
    db_batch_size: int = 50         # Books to accumulate before flushing to DB

    # ── Supported ebook formats ────────────────────────────────
    supported_formats: List[str] = [".pdf", ".epub", ".mobi", ".azw3", ".txt", ".cbz", ".html"]

    # pydantic-settings configuration: read BOOKBRAIN_* env vars and .env file
    model_config = {
        "env_prefix": "BOOKBRAIN_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    # ── Derived properties ─────────────────────────────────────

    @property
    def ebook_directories(self) -> List[Path]:
        """Parse ``ebook_dirs`` into a list of Paths.

        Supports two formats (auto-detected):
        - JSON array:          '["C:\\\\Books", "/volume1/ebooks"]'
          → preferred; handles paths that contain commas
        - Comma-separated:     '/home/user/books, /mnt/nas/ebooks'
          → legacy; kept for backward compatibility

        On Windows the paths are returned as-is (backslash preserved).
        On Unix/NAS they are returned as-is (forward slash preserved).
        """
        if not self.ebook_dirs:
            return []
        # Try JSON array first so paths containing commas are handled correctly.
        import json
        try:
            parsed = json.loads(self.ebook_dirs)
            if isinstance(parsed, list):
                return [Path(d) for d in parsed if isinstance(d, str) and d.strip()]
        except (json.JSONDecodeError, ValueError):
            pass
        # Fall back to comma-separated (original behaviour).
        return [Path(d.strip()) for d in self.ebook_dirs.split(",") if d.strip()]

    # ── Persistence helpers ────────────────────────────────────

    def save_to_disk(self) -> None:
        """Persist user-modifiable settings to ``data/user_settings.json``.

        Only a subset of settings (those editable via the Web UI) are saved.
        """
        import json
        settings_path = self.data_dir / "user_settings.json"
        data = {
            "ebook_dirs": self.ebook_dirs,
            "ocr_enabled": self.ocr_enabled,
            "ocr_language": self.ocr_language,
            "max_workers": self.max_workers,
            "ocr_max_pages": self.ocr_max_pages,
            "max_text_length": self.max_text_length,
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def load_from_disk(self) -> None:
        """Load persisted settings from ``data/user_settings.json`` if present.

        Called once during application startup (before routes are served).
        Silently skips if the file doesn't exist or is corrupt.
        """
        self.ensure_directories()
        settings_path = self.data_dir / "user_settings.json"
        if not settings_path.exists():
            return

        import json
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for key, value in data.items():
                    if hasattr(self, key):
                        setattr(self, key, value)
        except Exception as e:
            # Logger may not be initialised yet at this point
            print(f"Warning: Could not load user settings: {e}")

    def ensure_directories(self) -> None:
        """Create required data directories if they don't exist.

        Raises a ``PermissionError`` with a human-readable message when the
        process lacks write access (common on NAS/read-only mounts and inside
        packaged Tauri apps where the resource dir is not writable).
        """
        for directory in (self.data_dir, self.covers_dir, self.index_dir):
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except PermissionError as exc:
                raise PermissionError(
                    f"Cannot create data directory '{directory}': {exc}.\n"
                    "Set the BOOKBRAIN_DATA_DIR environment variable to a writable path "
                    "(e.g. export BOOKBRAIN_DATA_DIR=/volume1/homes/@bookbrain/data on Synology NAS)."
                ) from exc
            except OSError as exc:
                raise OSError(
                    f"Failed to create directory '{directory}': {exc}.\n"
                    "Check that the path is valid and the filesystem is mounted."
                ) from exc


# Singleton settings instance used throughout the application
settings = Settings()
