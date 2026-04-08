"""Metadata and text extraction from ebook files.

Provides format-specific extractors for:
  - PDF  (via PyMuPDF/fitz)
  - EPUB (via ebooklib)
  - TXT  (with encoding auto-detection: UTF-8 → GBK → Latin-1)
  - HTML (via BeautifulSoup)
  - MOBI/AZW3 (basic raw-text fallback)
  - CBZ  (comic book zip — images only, no text extraction)

Each extractor returns a ``BookMetadata`` dataclass containing the title,
author, text content, page-level chunks, cover image, and other metadata.
The main dispatch function ``extract_metadata()`` selects the right extractor
based on file extension.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BookMetadata:
    """Container for extracted ebook metadata and content.

    Attributes:
        title: Book title (falls back to filename stem if not found).
        author: Author name (defaults to "Unknown").
        chunks: List of text segments, each a dict with keys:
                ``content`` (str), ``page_number`` (int|None), ``location_tag`` (str|None).
                Used for page-level search indexing and vector embedding.
        text_content: Full concatenated text (truncated to max_text_length).
        cover_image: Raw bytes of the cover image (JPEG or PNG).
        cover_ext: File extension for the cover image (".jpg" or ".png").
    """
    title: str = ""
    author: str = "Unknown"
    isbn: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    language: Optional[str] = None
    description: Optional[str] = None
    page_count: Optional[int] = None
    text_content: str = ""
    chunks: list[dict] = field(default_factory=list)
    cover_image: Optional[bytes] = None
    cover_ext: str = ".jpg"


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def extract_pdf(file_path: Path, max_text_length: int = 2000000) -> BookMetadata:
    """Extract metadata, text, and cover from a PDF file using PyMuPDF (fitz).

    Text is chunked by page — each page becomes one entry in ``metadata.chunks``
    with its 1-based page number.  The cover is rendered from the first page
    at 2x zoom and saved as JPEG.
    """
    import fitz  # PyMuPDF

    metadata = BookMetadata()

    try:
        doc = fitz.open(str(file_path))

        # Metadata
        pdf_meta = doc.metadata or {}
        metadata.title = pdf_meta.get("title", "") or file_path.stem
        metadata.author = pdf_meta.get("author", "") or "Unknown"
        metadata.page_count = doc.page_count

        # Publisher and year from subject/keywords
        subject = pdf_meta.get("subject", "") or ""
        keywords = pdf_meta.get("keywords", "") or ""
        if subject:
            metadata.description = subject

        # Extract creation date for year
        creation_date = pdf_meta.get("creationDate", "")
        if creation_date and len(creation_date) >= 6:
            try:
                # Format: D:YYYYMMDDHHmmSS
                year_str = creation_date.replace("D:", "")[:4]
                metadata.year = int(year_str)
            except (ValueError, IndexError):
                pass

        # Text extraction (chunked by page)
        text_parts = []
        total_chars = 0
        for i, page in enumerate(doc):
            page_text = page.get_text()
            if page_text.strip():
                metadata.chunks.append({
                    "content": page_text,
                    "page_number": i + 1,
                    "location_tag": f"page_{i+1}"
                })
            text_parts.append(page_text)
            total_chars += len(page_text)
            if total_chars >= max_text_length:
                break

        metadata.text_content = "\n".join(text_parts)[:max_text_length]

        # Cover extraction (first page as image)
        try:
            if doc.page_count > 0:
                page = doc[0]
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom
                metadata.cover_image = pix.tobytes("jpeg")
                metadata.cover_ext = ".jpg"
        except Exception as e:
            logger.warning("Failed to extract PDF cover: %s", e)

        doc.close()

    except Exception as e:
        logger.error("Failed to extract PDF %s: %s", file_path, e)
        metadata.title = file_path.stem

    return metadata


def extract_epub(file_path: Path, max_text_length: int = 2000000) -> BookMetadata:
    """Extract metadata, text, and cover from an EPUB file using ebooklib.

    Text is chunked by EPUB document item (roughly one chapter per chunk).
    HTML tags are stripped using a simple parser.  The cover image is found
    by searching for an image item with "cover" in its name, falling back
    to the first image in the archive.
    """
    import ebooklib
    from ebooklib import epub
    from html.parser import HTMLParser
    import io

    metadata = BookMetadata()

    class HTMLStripper(HTMLParser):
        """Strip HTML tags and extract text."""
        def __init__(self):
            super().__init__()
            self.result = []
            self.skip = False

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self.skip = True

        def handle_endtag(self, tag):
            if tag in ("script", "style"):
                self.skip = False

        def handle_data(self, data):
            if not self.skip:
                self.result.append(data)

        def get_text(self) -> str:
            return " ".join(self.result)

    try:
        book = epub.read_epub(str(file_path), options={"ignore_ncx": True})

        # Metadata
        title = book.get_metadata("DC", "title")
        if title:
            metadata.title = title[0][0]
        else:
            metadata.title = file_path.stem

        creator = book.get_metadata("DC", "creator")
        if creator:
            metadata.author = creator[0][0]

        publisher = book.get_metadata("DC", "publisher")
        if publisher:
            metadata.publisher = publisher[0][0]

        language = book.get_metadata("DC", "language")
        if language:
            metadata.language = language[0][0]

        description = book.get_metadata("DC", "description")
        if description:
            metadata.description = description[0][0]

        identifier = book.get_metadata("DC", "identifier")
        if identifier:
            for ident in identifier:
                val = ident[0]
                # Check if it looks like an ISBN
                clean = val.replace("-", "").replace(" ", "")
                if clean.isdigit() and len(clean) in (10, 13):
                    metadata.isbn = val
                    break

        date = book.get_metadata("DC", "date")
        if date:
            try:
                metadata.year = int(date[0][0][:4])
            except (ValueError, IndexError):
                pass

        # Text extraction (chunked by chapter/item)
        text_parts = []
        total_chars = 0
        for i, item in enumerate(book.get_items_of_type(ebooklib.ITEM_DOCUMENT)):
            content = item.get_content()
            stripper = HTMLStripper()
            stripper.feed(content.decode("utf-8", errors="ignore"))
            text = stripper.get_text().strip()
            if text:
                metadata.chunks.append({
                    "content": text,
                    "page_number": i + 1,
                    "location_tag": item.get_name()
                })
                text_parts.append(text)
                total_chars += len(text)
                if total_chars >= max_text_length:
                    break

        metadata.text_content = "\n".join(text_parts)[:max_text_length]

        # Cover extraction
        try:
            cover_image = None
            # Try to find cover image
            for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
                name = item.get_name().lower()
                if "cover" in name:
                    cover_image = item.get_content()
                    if name.endswith(".png"):
                        metadata.cover_ext = ".png"
                    break

            if not cover_image:
                # Try first image
                images = list(book.get_items_of_type(ebooklib.ITEM_IMAGE))
                if images:
                    cover_image = images[0].get_content()
                    name = images[0].get_name().lower()
                    if name.endswith(".png"):
                        metadata.cover_ext = ".png"

            if cover_image:
                metadata.cover_image = cover_image
        except Exception as e:
            logger.warning("Failed to extract EPUB cover: %s", e)

    except Exception as e:
        logger.error("Failed to extract EPUB %s: %s", file_path, e)
        metadata.title = file_path.stem

    return metadata


def extract_txt(file_path: Path, max_text_length: int = 2000000) -> BookMetadata:
    """Extract text from a plain text file with encoding auto-detection.

    Tries UTF-8 first, then GBK (common for Chinese text), then Latin-1
    as a last resort.  Uses simple heuristics on the first few lines to
    guess the title and author.
    """
    metadata = BookMetadata(title=file_path.stem)
    try:
        # Try to read with UTF-8, fallback to other encodings
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = file_path.read_text(encoding="gbk")
            except UnicodeDecodeError:
                content = file_path.read_text(encoding="latin-1", errors="ignore")
                
        # Basic heuristic for title/author in first few lines
        lines = [line.strip() for line in content[:1000].split("\n") if line.strip()]
        if len(lines) >= 2:
            if len(lines[0]) < 100:
                metadata.title = lines[0]
            if "by" in lines[1].lower() or "author" in lines[1].lower():
                metadata.author = lines[1].replace("By", "").replace("by", "").replace("Author:", "").strip()
                
        metadata.text_content = content[:max_text_length]
    except Exception as e:
        logger.error("Failed to extract TXT %s: %s", file_path, e)
        
    return metadata


def extract_html(file_path: Path, max_text_length: int = 2000000) -> BookMetadata:
    """Extract text from HTML file."""
    metadata = BookMetadata(title=file_path.stem)
    try:
        from bs4 import BeautifulSoup
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = file_path.read_text(encoding="gbk", errors="ignore")
            
        soup = BeautifulSoup(content, "html.parser")
        
        if soup.title:
            metadata.title = soup.title.string.strip()
            
        text = soup.get_text(separator="\n")
        # Clean up multiple newlines
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        metadata.text_content = "\n".join(lines)[:max_text_length]
    except Exception as e:
        logger.error("Failed to extract HTML %s: %s", file_path, e)
        
    return metadata


def extract_mobi_azw3(file_path: Path, max_text_length: int = 2000000) -> BookMetadata:
    """Basic text extraction for Kindle formats (MOBI/AZW3).

    Uses a crude approach: reads raw bytes, filters for printable ASCII
    characters, and strips XML/HTML tags.  This is a fallback implementation;
    for better results, consider using Calibre's ``ebook-convert`` CLI.
    """
    metadata = BookMetadata(title=file_path.stem)
    try:
        # We read raw bytes and extract visible ASCII/UTF8 text as a brutal fallback
        # In a production app, use 'mobi' or 'calibre' CLI tools here
        raw = file_path.read_bytes()
        # Very crude ascii string extraction for basic searchability
        import string
        printable = set(string.printable.encode())
        text_bytes = bytearray()
        for b in raw[:max_text_length * 2]: # search first chunk
            if b in printable:
                text_bytes.append(b)
        
        import re
        text = text_bytes.decode('ascii', errors='ignore')
        # Remove massive whitespace blocks and XML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        metadata.text_content = text[:max_text_length]
        
    except Exception as e:
        logger.error("Failed to extract MOBI/AZW3 %s: %s", file_path, e)
        
    return metadata


def extract_cbz(file_path: Path) -> BookMetadata:
    """Extract metadata from a CBZ (Comic Book Zip) archive.

    CBZ files contain only images (no text), so only page count and cover
    image are extracted.  The first image (alphabetically sorted) is used
    as the cover.
    """
    import zipfile
    metadata = BookMetadata(title=file_path.stem)
    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            # Count images for page count
            img_exts = ('.jpg', '.jpeg', '.png', '.webp')
            images = [f for f in zf.namelist() if f.lower().endswith(img_exts) and not f.startswith('__MACOSX/')]
            metadata.page_count = len(images)
            
            # Try to grab first image as cover
            if images:
                images.sort() # Ensure we get the first page
                cover_filename = images[0]
                metadata.cover_image = zf.read(cover_filename)
                metadata.cover_ext = Path(cover_filename).suffix.lower()
    except Exception as e:
        logger.error("Failed to extract CBZ %s: %s", file_path, e)
        
    return metadata


def extract_metadata(file_path: Path, max_text_length: int = 2000000) -> BookMetadata:
    """Dispatch to the appropriate format-specific extractor based on file extension.

    This is the main entry point for extraction.  Returns a BookMetadata
    dataclass regardless of format; unsupported formats return a minimal
    result with only the filename as the title.
    """
    ext = file_path.suffix.lower()

    if ext == ".pdf":
        return extract_pdf(file_path, max_text_length)
    elif ext == ".epub":
        return extract_epub(file_path, max_text_length)
    elif ext == ".txt":
        return extract_txt(file_path, max_text_length)
    elif ext in (".htm", ".html"):
        return extract_html(file_path, max_text_length)
    elif ext in (".mobi", ".azw3"):
        return extract_mobi_azw3(file_path, max_text_length)
    elif ext == ".cbz":
        return extract_cbz(file_path)
    else:
        logger.warning("Unsupported format: %s", ext)
        return BookMetadata(title=file_path.stem)
