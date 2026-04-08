# ==============================================================
# BookBrain Dockerfile — Multi-stage build
#
# Stage 1 (builder): Install Python dependencies into user site-packages
# Stage 2 (runtime): Slim image with Tesseract OCR + app code
#
# Usage:
#   docker build -t bookbrain -f docker/Dockerfile .
#   docker run -p 8000:8000 -v /path/to/ebooks:/ebooks:ro bookbrain
# ==============================================================

# -- Stage 1: Build dependencies --
FROM python:3.12-slim AS builder

WORKDIR /app

COPY server/requirements.txt .
# Install Python packages to user directory (avoids polluting system site-packages)
RUN pip install --no-cache-dir --user -r requirements.txt

# -- Stage 2: Runtime image --
FROM python:3.12-slim

# Install Tesseract OCR with English and Chinese language packs,
# plus OpenGL/GLib libraries required by PyMuPDF and EasyOCR.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-chi-sim \
        libgl1-mesa-glx \
        libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python packages from the builder stage
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy the backend application code
COPY server/ ./

# Create persistent data directories (mounted as a Docker volume)
RUN mkdir -p /data/covers /data/index

# Default environment variables for containerised deployment.
# These point all data storage to /data (a Docker volume) and
# expect ebooks to be mounted at /ebooks.
ENV BOOKBRAIN_DATABASE_URL=sqlite+aiosqlite:///data/bookbrain.db
ENV BOOKBRAIN_DATA_DIR=/data
ENV BOOKBRAIN_COVERS_DIR=/data/covers
ENV BOOKBRAIN_INDEX_DIR=/data/index
ENV BOOKBRAIN_EBOOK_DIRS=/ebooks

EXPOSE 8000

# Run the FastAPI app with Uvicorn
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
