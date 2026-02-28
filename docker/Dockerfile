# -- Build stage --
FROM python:3.12-slim AS builder

WORKDIR /app

COPY server/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# -- Runtime stage --
FROM python:3.12-slim

# Install Tesseract OCR
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-chi-sim \
        libgl1-mesa-glx \
        libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY server/ ./

# Create data directories
RUN mkdir -p /data/covers /data/index

# Environment variables
ENV BOOKBRAIN_DATABASE_URL=sqlite+aiosqlite:///data/bookbrain.db
ENV BOOKBRAIN_DATA_DIR=/data
ENV BOOKBRAIN_COVERS_DIR=/data/covers
ENV BOOKBRAIN_INDEX_DIR=/data/index
ENV BOOKBRAIN_EBOOK_DIRS=/ebooks

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
