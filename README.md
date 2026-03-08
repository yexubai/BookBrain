# BookBrain 📚

Smart ebook management system with OCR, automatic classification, and semantic search.

## Features

- **Multi-format support** — PDF and EPUB metadata/text extraction
- **OCR** — Automatic Tesseract OCR for scanned PDFs (English + Chinese)
- **Smart classification** — Rule-based + ML zero-shot classification into 10+ categories
- **Semantic search** — FAISS vector search powered by sentence-transformers
- **Modern UI** — Dark theme React frontend with grid/list views, category tree, search
- **Desktop app** — Tauri 2.x wrapper for native Windows/macOS/Linux desktop experience
- **NAS deployment** — Docker Compose ready for Synology NAS

## Architecture

```
BookBrain/
├── server/                 # Python FastAPI backend
│   ├── main.py             # App entry point
│   ├── config.py           # Settings (env vars)
│   ├── db/                 # SQLAlchemy models & CRUD
│   ├── ingest/             # Scanner, extractor, OCR, pipeline
│   ├── classify/           # Rule + ML classifier
│   ├── search/             # FAISS vector store
│   └── api/                # REST routes & schemas
├── client/                 # React + Vite frontend + Tauri desktop
│   ├── src/                # React components & pages
│   └── src-tauri/          # Tauri Rust shell (desktop app)
└── docker/                 # Dockerfile & docker-compose.yml
```

## Quick Start

### Backend

```bash
cd server
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000/docs for Swagger UI.

### Frontend (Web)

```bash
cd client
npm install
npm run dev
```

Open http://localhost:1420

### Desktop App (Tauri)

Requires [Rust](https://rustup.rs/) installed.

```bash
cd client
npm run tauri:dev     # Development with hot-reload
npm run tauri:build   # Build .exe / .dmg / .deb installer
```

### Docker (NAS)

```bash
cd docker
docker-compose up -d
```

## Configuration

Set via environment variables (prefix `BOOKBRAIN_`) or `.env` file:

| Variable | Default | Description |
|---|---|---|
| `BOOKBRAIN_EBOOK_DIRS` | (empty) | Comma-separated ebook directories |
| `BOOKBRAIN_OCR_ENABLED` | `true` | Enable Tesseract OCR |
| `BOOKBRAIN_OCR_LANGUAGE` | `eng+chi_sim` | OCR language codes |
| `BOOKBRAIN_MAX_WORKERS` | `4` | Processing threads |
| `BOOKBRAIN_EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Embedding model |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/books` | List books (paginated, filterable) |
| `GET` | `/api/books/{id}` | Book details |
| `GET` | `/api/books/{id}/cover` | Cover image |
| `DELETE` | `/api/books/{id}` | Delete book record |
| `GET` | `/api/categories` | Category tree |
| `GET` | `/api/search?q=` | Semantic search |
| `POST` | `/api/ingest` | Trigger import |
| `GET` | `/api/ingest/status` | Import progress |
| `GET/PUT` | `/api/settings` | Settings |
| `GET` | `/api/stats` | Library statistics |

## Dependencies

- Python 3.10+, Node.js 18+
- [Rust](https://rustup.rs/) (for Tauri desktop app)
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (for scanned PDFs)
- sentence-transformers model (~90MB, auto-downloaded)
