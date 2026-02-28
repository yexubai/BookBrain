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
    ocr_language: str = "eng+chi_sim"
    ocr_max_pages: int = 10  # Max pages to OCR per book
    scanned_text_threshold: float = 0.1  # Below this ratio, consider PDF as scanned

    # ML Model
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dimension: int = 384

    # Processing
    max_workers: int = Field(default=4, description="Max threads for processing")
    max_text_length: int = 50000  # Max chars of text to store per book
    batch_size: int = 32  # Batch size for embedding

    # Supported formats
    supported_formats: List[str] = [".pdf", ".epub"]

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

    def ensure_directories(self) -> None:
        """Create required directories."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.covers_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
