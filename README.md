# BookBrain 📚

Smart ebook management system with OCR, automatic classification, full-text search, and semantic search.

## Features

- **Multi-format support** — Metadata and text extraction for PDF, EPUB, MOBI, AZW3, TXT, HTML, CBZ
- **OCR** — Automatic scanned PDF detection with EasyOCR (supports 80+ languages including English and Chinese)
- **Smart classification** — Rule-based keyword engine + ML zero-shot classification across 10+ categories (Programming, Data Science, AI, Math, Literature, etc.)
- **Dual-engine search** — FTS5 full-text keyword search + FAISS vector semantic search, with prefix matching and fuzzy queries
- **Page-level navigation** — Search results pinpoint exact page/chapter, click to jump directly into the reader
- **Built-in reader** — Online PDF/EPUB reader with highlight annotations and notes
- **Dark theme UI** — React frontend with grid/list views, category tree, real-time search
- **Desktop app** — Tauri 2.x wrapper for native Windows/macOS/Linux desktop experience
- **NAS deployment** — Docker Compose ready for Synology and other NAS devices

## Architecture

```
BookBrain/
├── server/                     # Python FastAPI backend
│   ├── main.py                 # App entry point, lifespan management (startup/shutdown)
│   ├── config.py               # Settings management (env vars + persistent JSON)
│   ├── db/                     # Database layer
│   │   ├── database.py         # SQLAlchemy async engine, session factory, FTS5 index init
│   │   ├── models.py           # ORM models (Book, Chunk, Annotation)
│   │   └── crud.py             # CRUD operations + FTS5 full-text search + ILIKE fallback
│   ├── ingest/                 # Import pipeline
│   │   ├── scanner.py          # Recursive directory scanner, supports 7 ebook formats
│   │   ├── extractor.py        # Format-specific extractors (PDF/EPUB/TXT/HTML/MOBI/CBZ)
│   │   ├── ocr.py              # EasyOCR processor, auto-detects scanned PDFs
│   │   └── pipeline.py         # Multi-threaded ingest pipeline (scan→extract→OCR→classify→embed→store)
│   ├── classify/               # Classification engine
│   │   └── classifier.py       # Two-tier classifier: keyword rules first, sentence-transformers zero-shot fallback
│   ├── search/                 # Search engine
│   │   └── vector_store.py     # FAISS HNSW vector index with incremental add, bulk rebuild, self-healing
│   └── api/                    # REST API layer
│       ├── routes.py           # All API routes (books CRUD, search, ingest, settings, admin)
│       └── schemas.py          # Pydantic request/response models
├── client/                     # Frontend + desktop app
│   ├── src/                    # React + TypeScript source
│   │   ├── api.ts              # API client (supports local/remote backend switching)
│   │   ├── App.tsx             # Root router (Library / Search / Ingest / Settings / Reader)
│   │   ├── pages/
│   │   │   ├── LibraryPage.tsx # Library home (pagination, filtering, grid/list views)
│   │   │   ├── SearchPage.tsx  # Unified search page (keyword + semantic, 500ms debounce)
│   │   │   ├── IngestPage.tsx  # Import management (directory selection, progress tracking)
│   │   │   ├── SettingsPage.tsx# Settings page (OCR, directories, worker threads, etc.)
│   │   │   └── ReaderPage.tsx  # Reader page (PDF/EPUB rendering, annotations)
│   │   └── components/
│   │       ├── Topbar.tsx      # Top bar (search input, navigation)
│   │       ├── Sidebar.tsx     # Sidebar (category tree)
│   │       ├── BookDetail.tsx  # Book detail modal
│   │       └── FileBrowser.tsx # Server-side file browser (for directory selection)
│   └── src-tauri/              # Tauri Rust shell (desktop app packaging)
│       ├── tauri.conf.json     # Tauri config (window, permissions, build)
│       └── src/                # Rust entry code
└── docker/                     # Docker deployment
    ├── Dockerfile              # Multi-stage build (Python 3.12 + Tesseract OCR)
    └── docker-compose.yml      # One-click NAS deployment config
```

## Tech Stack

| Layer | Technology | Description |
|-------|-----------|-------------|
| **Backend** | FastAPI + Uvicorn | Async Python web framework |
| **Database** | SQLite + aiosqlite | Lightweight async database, WAL mode for concurrent reads/writes |
| **Full-text search** | SQLite FTS5 | Built-in full-text search engine, unicode61 tokenizer for CJK support |
| **Vector search** | FAISS (HNSW) | Facebook AI Similarity Search, HNSW algorithm for approximate nearest neighbor |
| **Text embedding** | sentence-transformers | Multilingual embedding model `paraphrase-multilingual-MiniLM-L12-v2` |
| **PDF processing** | PyMuPDF (fitz) | High-performance PDF parsing, text extraction, cover rendering |
| **EPUB processing** | ebooklib | EPUB metadata and content extraction |
| **OCR** | EasyOCR + PyTorch | Deep learning OCR, supports 80+ languages |
| **Classification** | Rules + zero-shot ML | Keyword matching first, sentence-transformers semantic classification fallback |
| **Frontend** | React 18 + TypeScript | Vite build, dark theme |
| **Desktop app** | Tauri 2.x (Rust) | Native cross-platform desktop app, lighter than Electron |
| **Containerization** | Docker | Multi-stage build, NAS-ready deployment |

## Quick Start

### Backend

```bash
cd server
pip install -r requirements.txt

# Development mode (hot-reload)
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000/docs for Swagger API docs.

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
npm run tauri:build   # Build installer (.exe / .dmg / .deb)
```

### Docker (NAS)

```bash
cd docker
docker-compose up -d
```

## Configuration

Set via environment variables (prefix `BOOKBRAIN_`) or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `BOOKBRAIN_EBOOK_DIRS` | (empty) | Comma-separated ebook directories |
| `BOOKBRAIN_OCR_ENABLED` | `true` | Enable OCR for scanned PDF auto-detection |
| `BOOKBRAIN_OCR_LANGUAGE` | `ch_sim+en` | OCR language codes (EasyOCR format) |
| `BOOKBRAIN_MAX_WORKERS` | CPU cores / 2 | Parallel processing threads |
| `BOOKBRAIN_EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Text embedding model (~90MB, auto-downloaded) |
| `BOOKBRAIN_DATABASE_URL` | `sqlite+aiosqlite:///./data/bookbrain.db` | Database connection URL |
| `BOOKBRAIN_DEBUG` | `false` | Debug mode (verbose logging + SQL echo) |
| `BOOKBRAIN_MAX_TEXT_LENGTH` | `2000000` | Max characters to extract per book |
| `BOOKBRAIN_BATCH_SIZE` | `32` | Embedding batch size |
| `BOOKBRAIN_DB_BATCH_SIZE` | `50` | Database batch commit size |

Runtime settings can also be modified via the Settings page in the Web UI, persisted to `data/user_settings.json`.

## API Endpoints

### Books

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/books` | List books (paginated, category/format filter, keyword search, sort) |
| `GET` | `/api/books/{id}` | Book details |
| `PUT` | `/api/books/{id}` | Update book metadata (title, author, category, etc.) |
| `DELETE` | `/api/books/{id}` | Delete book record (does not delete the source file) |
| `GET` | `/api/books/{id}/cover` | Cover image (supports ETag caching) |
| `GET` | `/api/books/{id}/file` | Serve original ebook file for reading/download |

### Annotations

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/books/{id}/annotations` | List all annotations for a book |
| `POST` | `/api/books/{id}/annotations` | Create annotation (highlight + note) |
| `PUT` | `/api/annotations/{id}` | Update annotation content or color |
| `DELETE` | `/api/annotations/{id}` | Delete annotation |

### Search

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/search?q=` | Pure semantic search (FAISS vector similarity) |
| `GET` | `/api/search/unified?q=` | Unified search (FTS5 keyword + FAISS semantic, deduplicated, page-level results) |

### Import

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/ingest` | Trigger import (optional: specify directories, force rescan) |
| `GET` | `/api/ingest/status` | Import progress (file count, percentage, current file, error list) |

### Other

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/categories` | Category tree (with subcategories and counts) |
| `GET` | `/api/stats` | Library statistics (total books, format distribution, total size) |
| `GET/PUT` | `/api/settings` | Read/update settings |
| `GET` | `/api/admin/browse?path=` | Server-side file browser (for directory selection) |
| `POST` | `/api/admin/rebuild-fts` | Rebuild FTS5 full-text index |
| `POST` | `/api/admin/rebuild-vectors` | Rebuild FAISS vector index |

## Search Architecture

BookBrain uses a dual-engine search architecture:

```
User input: "machine learning"
        │
        ├──→ FTS5 keyword search (chunks_fts table)
        │     ├── Prefix matching: "machine"* "learning"*
        │     ├── Phrase matching: "machine learning"
        │     └── Fallback: ILIKE fuzzy search (CJK compatible)
        │
        └──→ FAISS semantic search
              ├── sentence-transformers encodes query vector
              └── HNSW approximate nearest neighbor retrieval (chunk-level)
        │
        ├── Deduplicate & merge (keyword results take priority)
        └── Return results (book + page number + context snippet + source label)
```

- **Keyword search**: Exact match on title, author, filename, and body text; supports prefix completion
- **Semantic search**: Matches by meaning similarity, finds relevant results even when exact terms differ
- **Page-level granularity**: Results pinpoint specific page/chapter, with direct jump-to-read support

## Ingest Pipeline

```
Scan directories → Skip already-processed files → Multi-threaded parallel processing:
  ┌─────────────────────────────────────────────────┐
  │  Extract metadata (title, author, cover, pages) │
  │  Extract full text (split by page/chapter → Chunk) │
  │  Detect scanned PDF → EasyOCR recognition       │
  │  Rule-based classification → ML zero-shot fallback │
  └─────────────────────────────────────────────────┘
  → Batch DB commit → Batch vector embedding → Save FAISS index
```

- Supports incremental import (skips processed files) and force rescan
- Batched database commits (every 50 books) + batched vector embeddings (every 32 chunks) to reduce I/O overhead
- Runs asynchronously in the background; query progress in real-time via API

## Database Schema

```
books (main book table)
├── id, title, author, isbn, publisher, year, language, description
├── format, file_path, file_size, file_hash
├── cover_path, category, subcategory, tags
├── summary, text_content, page_count
└── created_at, updated_at

chunks (text segment table - page/chapter level)
├── id, book_id (FK → books)
├── page_number, location_tag
├── content (segment text)
└── vector_id (FAISS index ID)

annotations (highlight & notes table)
├── id, book_id (FK → books)
├── location (EPUB CFI / PDF Page+Rect)
├── selected_text, note, color
└── created_at, updated_at

books_fts (FTS5 virtual table - book-level full-text index)
chunks_fts (FTS5 virtual table - chunk-level full-text index)
```

## Dependencies

- Python 3.10+, Node.js 18+
- [Rust](https://rustup.rs/) (for Tauri desktop app)
- [PyTorch](https://pytorch.org/) (required by EasyOCR and sentence-transformers)
- sentence-transformers embedding model (~90MB, auto-downloaded on first run)
- Users in China automatically use HuggingFace mirror (`hf-mirror.com`)

## License

[MIT](LICENSE)
