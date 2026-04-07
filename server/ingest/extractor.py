"""Metadata and text extraction from ebook files."""

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BookMetadata:
    """Extracted book metadata."""
    title: str = ""
    author: str = "Unknown"
    isbn: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    language: Optional[str] = None
    description: Optional[str] = None
    page_count: Optional[int] = None
    text_content: str = ""
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
    """Extract metadata and text from a PDF file using PyMuPDF."""
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

        # Text extraction
        text_parts = []
        total_chars = 0
        for page in doc:
            page_text = page.get_text()
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
    """Extract metadata and text from an EPUB file."""
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

        # Text extraction
        text_parts = []
        total_chars = 0
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            content = item.get_content()
            stripper = HTMLStripper()
            stripper.feed(content.decode("utf-8", errors="ignore"))
            text = stripper.get_text().strip()
            if text:
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
    """Extract metadata and text from a TXT file."""
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
    """Basic extraction for Kindle formats (MOBI/AZW3).
    Requires 'mobi' package for full extraction, doing basic fallback for now.
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
    """Extract metadata from CBZ (Comic Book Zip). Text extraction skipped as it's images."""
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
    """Extract metadata and text from an ebook file.

    Dispatches to format-specific extractors.
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
