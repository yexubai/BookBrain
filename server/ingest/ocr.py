"""OCR processing for scanned PDF files."""

import logging
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


class OCRProcessor:
    """OCR processor using Tesseract for scanned PDFs."""

    def __init__(self):
        self.enabled = settings.ocr_enabled
        self.language = settings.ocr_language
        self.max_pages = settings.ocr_max_pages
        self.text_threshold = settings.scanned_text_threshold

    def is_scanned_pdf(self, file_path: Path, text_content: str, page_count: int) -> bool:
        """Detect if a PDF is likely scanned (has very little text).

        Args:
            file_path: Path to the PDF file.
            text_content: Already extracted text content.
            page_count: Number of pages in the PDF.

        Returns:
            True if the PDF appears to be scanned.
        """
        if not page_count or page_count == 0:
            return False

        # Calculate text-to-page ratio
        chars_per_page = len(text_content) / page_count
        # A normal page has ~2000-3000 chars; scanned pages have very few
        is_scanned = chars_per_page < 100 * self.text_threshold
        if is_scanned:
            logger.info(
                "PDF appears scanned: %s (%.1f chars/page)",
                file_path.name, chars_per_page,
            )
        return is_scanned

    def process_pdf(self, file_path: Path, max_text_length: int = 50000) -> Optional[str]:
        """Run OCR on a PDF file and return extracted text.

        Args:
            file_path: Path to the PDF file.
            max_text_length: Maximum characters to extract.

        Returns:
            Extracted text, or None if OCR fails/is disabled.
        """
        if not self.enabled:
            logger.info("OCR is disabled, skipping %s", file_path.name)
            return None

        try:
            import fitz  # PyMuPDF
            import pytesseract
            from PIL import Image
            import io
        except ImportError as e:
            logger.error("OCR dependencies not available: %s", e)
            return None

        try:
            doc = fitz.open(str(file_path))
            pages_to_process = min(doc.page_count, self.max_pages)
            text_parts = []
            total_chars = 0

            logger.info(
                "Running OCR on %s (%d pages)",
                file_path.name, pages_to_process,
            )

            for page_idx in range(pages_to_process):
                page = doc[page_idx]

                # Render page to image at 300 DPI
                mat = fitz.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(matrix=mat)

                # Convert to PIL Image
                img = Image.open(io.BytesIO(pix.tobytes("png")))

                # Run Tesseract OCR
                text = pytesseract.image_to_string(
                    img,
                    lang=self.language,
                    config="--psm 1",  # Automatic page segmentation with OSD
                )

                if text.strip():
                    text_parts.append(text.strip())
                    total_chars += len(text)
                    if total_chars >= max_text_length:
                        break

            doc.close()

            result = "\n\n".join(text_parts)[:max_text_length]
            logger.info(
                "OCR extracted %d chars from %s",
                len(result), file_path.name,
            )
            return result

        except Exception as e:
            logger.error("OCR failed for %s: %s", file_path.name, e)
            return None
