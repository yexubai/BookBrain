"""OCR processing for scanned PDF files."""

import logging
from pathlib import Path
from typing import Optional
import threading

from config import settings

logger = logging.getLogger(__name__)


class OCRProcessor:
    """OCR processor using easyocr for standalone scanned PDFs."""

    _shared_reader = None
    _load_lock = threading.Lock()

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

    def process_pdf(self, file_path: Path, max_text_length: int = 2000000) -> Optional[str]:
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
            import torch
            import easyocr
            from PIL import Image
            import io
            import numpy as np
        except ImportError as e:
            logger.error("OCR dependencies not available: %s", e)
            return None

        try:
            # Thread-safe lazy initialization of easyocr Reader
            if OCRProcessor._shared_reader is None:
                with OCRProcessor._load_lock:
                    if OCRProcessor._shared_reader is None:
                        gpu_available = torch.cuda.is_available()
                        logger.info(
                            "Initializing easyocr Reader (GPU: %s, Lang: %s)", 
                            gpu_available, self.language
                        )
                        # Convert '+' separated langs to list for easyocr
                        langs = self.language.split("+")
                        OCRProcessor._shared_reader = easyocr.Reader(langs, gpu=gpu_available)
                        logger.info("easyocr Reader initialized successfully")

            doc = fitz.open(str(file_path))
            pages_to_process = min(doc.page_count, self.max_pages)
            text_parts = []
            total_chars = 0

            logger.info(
                "Running easyocr on %s (%d pages)",
                file_path.name, pages_to_process,
            )

            for page_idx in range(pages_to_process):
                page = doc[page_idx]

                # Render page to image at 200 DPI (good balance for easyocr)
                mat = fitz.Matrix(200 / 72, 200 / 72)
                pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)

                # Convert to numpy array for easyocr
                img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)
                
                # Run easyocr
                results = OCRProcessor._shared_reader.readtext(img_data, detail=0)
                text = " ".join(results)

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
