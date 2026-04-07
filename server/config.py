"""BookBrain configuration management."""

import os
from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Application
    app_name: str = "BookBrain"
    app_version: str = "0.1.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/bookbrain.db",
        description="SQLAlchemy database URL"
    )

    # Ebook Directories (comma-separated paths)
    ebook_dirs: str = Field(
        default="",
        description="Comma-separated list of directories to scan for ebooks"
    )

    # File Storage
    data_dir: Path = Field(default=Path("./data"), description="Data directory")
    covers_dir: Path = Field(default=Path("./data/covers"), description="Cover images directory")
    index_dir: Path = Field(default=Path("./data/index"), description="FAISS index directory")

    # OCR
    ocr_enabled: bool = True
    ocr_language: str = "ch_sim+en"  # EasyOCR language codes
    ocr_max_pages: int = 20
    scanned_text_threshold: float = 0.1  # Below this ratio, consider PDF as scanned

    # ML Model
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dimension: int = 384

    # Processing
    max_workers: int = Field(
        default=max(1, (os.cpu_count() or 4) // 2), 
        description="Max threads for processing (half of logical cores)"
    )
    max_text_length: int = 2000000  # Max chars of text to store per book (full-text search)
    batch_size: int = 32          # Batch size for embedding
    db_batch_size: int = 50       # Books to accumulate before a batch DB commit

    # Supported formats
    supported_formats: List[str] = [".pdf", ".epub", ".mobi", ".azw3", ".txt", ".cbz", ".html"]

    model_config = {
        "env_prefix": "BOOKBRAIN_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    @property
    def ebook_directories(self) -> List[Path]:
        """Parse comma-separated ebook directories."""
        if not self.ebook_dirs:
            return []
        return [Path(d.strip()) for d in self.ebook_dirs.split(",") if d.strip()]

    def save_to_disk(self) -> None:
        """Save settings to a JSON file."""
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
        """Load settings from a JSON file if it exists."""
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
            # We don't have a logger initialized yet in config.py easily, but it's safe to print here
            print(f"Warning: Could not load user settings: {e}")

    def ensure_directories(self) -> None:
        """Create required directories."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.covers_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
