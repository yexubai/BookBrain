/**
 * API client for BookBrain backend.
 *
 * Supports two deployment modes:
 *   - **Local/sidecar**: Backend runs on localhost:8000 alongside the frontend.
 *     In Vite dev mode (port 1420), requests go through Vite's proxy as "/api".
 *   - **Remote/NAS**: User configures a custom backend URL via the Settings page.
 *     The URL is persisted in localStorage and used for all API calls.
 *
 * The `api` object at the bottom provides typed methods for every backend endpoint.
 */

/** Default backend URL when no custom URL is configured. */
const DEFAULT_BACKEND = 'http://localhost:8000';

/** localStorage key for persisting the user-configured backend URL. */
const STORAGE_KEY = 'bookbrain_backend_url';

/** Get the configured backend URL (from localStorage or default). */
export function getBackendUrl(): string {
    if (typeof window !== 'undefined') {
        return localStorage.getItem(STORAGE_KEY) || DEFAULT_BACKEND;
    }
    return DEFAULT_BACKEND;
}

/** Set and persist the backend URL (strips trailing slashes). */
export function setBackendUrl(url: string) {
    const cleaned = url.replace(/\/+$/, '');
    localStorage.setItem(STORAGE_KEY, cleaned);
}

/** Check if running inside the Tauri desktop app (vs. browser). */
export function isTauri(): boolean {
    return !!(window as any).__TAURI_INTERNALS__;
}

/**
 * Resolve the API base URL.
 * - In Vite dev mode (port 1420): use "/api" (proxied by Vite to localhost:8000)
 * - In Tauri or production: use the configured backend URL + "/api"
 */
function getApiBase(): string {
    if (!isTauri() && window.location.port === '1420') {
        return '/api';
    }
    return `${getBackendUrl()}/api`;
}

// ─── TypeScript Interfaces ────────────────────────────
// These mirror the Pydantic schemas defined in server/api/schemas.py.

export interface Book {
    id: number;
    title: string;
    author: string;
    isbn?: string;
    publisher?: string;
    year?: number;
    language?: string;
    description?: string;
    format: string;
    file_path: string;
    file_size: number;
    cover_path?: string;
    category: string;
    subcategory?: string;
    tags?: string;
    summary?: string;
    page_count?: number;
    ocr_processed: boolean;
    processing_status: string;
    created_at: string;
    updated_at: string;
}

export interface BookListResponse {
    books: Book[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
}

export interface Category {
    name: string;
    count: number;
    subcategories: { name: string; count: number }[];
}

export interface SearchResult {
    book: Book;
    score: number;
    context?: string;
}

export interface SearchResponse {
    query: string;
    results: SearchResult[];
    total: number;
}

export interface UnifiedSearchResult {
    book: Book;
    score: number;
    /** "keyword" = FTS5 title/author/filename/content match; "semantic" = vector similarity */
    source: 'keyword' | 'semantic';
    filename?: string;
    context?: string;
    page_number?: number;
    location_tag?: string;
}

export interface UnifiedSearchResponse {
    query: string;
    results: UnifiedSearchResult[];
    total: number;
    keyword_count: number;
    semantic_count: number;
}

export interface IngestStatus {
    is_running: boolean;
    total_files: number;
    processed_files: number;
    skipped_files: number;
    failed_files: number;
    current_file?: string;
    errors: string[];
    progress_percent: number;
}

export interface FileBrowserItem {
    name: string;
    path: string;
    is_dir: boolean;
    size?: number;
}

export interface FileBrowserResponse {
    current_path: string;
    parent_path?: string;
    items: FileBrowserItem[];
}

export interface Settings {
    ebook_dirs: string;
    ocr_enabled: boolean;
    ocr_language: string;
    embedding_model: string;
    max_workers: number;
    data_dir: string;
}

export interface Annotation {
    id: number;
    book_id: number;
    location: string;
    selected_text: string;
    note: string;
    color: string;
    created_at: string;
    updated_at: string;
}

export interface Stats {
    total_books: number;
    formats: Record<string, number>;
    category_count: number;
    total_size_bytes: number;
}

// ─── API Fetch Helper ─────────────────────────────────

/**
 * Generic fetch wrapper that prepends the API base URL, sets JSON headers,
 * and parses the response.  Throws an Error with the server's detail message
 * on non-2xx responses.
 */
async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
    const base = getApiBase();
    const res = await fetch(`${base}${url}`, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'API error');
    }
    return res.json();
}

/**
 * Quick health check — returns true if the backend root endpoint responds
 * within 3 seconds.  Used by the Settings page to validate backend URLs.
 */
export async function checkBackendHealth(): Promise<boolean> {
    try {
        const url = getBackendUrl();
        const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
        return res.ok;
    } catch {
        return false;
    }
}

// ─── API Methods ──────────────────────────────────────
// Each method maps 1:1 to a backend endpoint defined in server/api/routes.py.

export const api = {
    // --- Books ---
    getBooks: (params: {
        page?: number;
        page_size?: number;
        category?: string;
        format?: string;
        q?: string;
        sort_by?: string;
        sort_order?: string;
    }) => {
        const qs = new URLSearchParams();
        Object.entries(params).forEach(([k, v]) => {
            if (v !== undefined && v !== null && v !== '') qs.set(k, String(v));
        });
        return apiFetch<BookListResponse>(`/books?${qs}`);
    },

    getBook: (id: number) => apiFetch<Book>(`/books/${id}`),

    updateBook: (id: number, data: Partial<Book>) =>
        apiFetch<Book>(`/books/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        }),

    deleteBook: (id: number) =>
        apiFetch<{ message: string }>(`/books/${id}`, { method: 'DELETE' }),

    /** Build a direct URL to a book's cover image (used in <img src>). */
    getCoverUrl: (id: number) => `${getApiBase()}/books/${id}/cover?v=${id}`,

    /** Build a direct URL to the original ebook file (for the reader). */
    getFileUrl: (id: number) => `${getApiBase()}/books/${id}/file`,

    // --- Categories ---
    getCategories: () => apiFetch<Category[]>('/categories'),

    // --- Search ---
    /** Pure semantic search (FAISS vector similarity only). */
    search: (q: string, limit?: number) => {
        const qs = new URLSearchParams({ q });
        if (limit) qs.set('limit', String(limit));
        return apiFetch<SearchResponse>(`/search?${qs}`);
    },

    /** Unified search combining FTS5 keyword + FAISS semantic results. */
    searchUnified: (q: string, limit?: number) => {
        const qs = new URLSearchParams({ q });
        if (limit) qs.set('limit', String(limit));
        return apiFetch<UnifiedSearchResponse>(`/search/unified?${qs}`);
    },

    // --- Ingest ---
    /** Start the import pipeline (runs in the background on the server). */
    triggerIngest: (params: { directories?: string[]; force_rescan?: boolean } = {}) =>
        apiFetch<IngestStatus>('/ingest', {
            method: 'POST',
            body: JSON.stringify(params),
        }),

    /** Poll the current import progress (file counts, percentage, errors). */
    getIngestStatus: () => apiFetch<IngestStatus>('/ingest/status'),

    // --- Settings ---
    getSettings: () => apiFetch<Settings>('/settings'),

    updateSettings: (data: Partial<Settings>) =>
        apiFetch<Settings>('/settings', {
            method: 'PUT',
            body: JSON.stringify(data),
        }),

    // --- Stats ---
    /** Library statistics (total books, format distribution, total size). */
    getStats: () => apiFetch<Stats>('/stats'),

    // --- Admin ---
    browseFiles: (path?: string) => {
        const qs = new URLSearchParams();
        if (path) qs.set('path', path);
        return apiFetch<FileBrowserResponse>(`/admin/browse?${qs}`);
    },

    // --- Annotations ---
    getAnnotations: (bookId: number) => apiFetch<Annotation[]>(`/books/${bookId}/annotations`),
    
    createAnnotation: (bookId: number, data: { location: string; selected_text: string; note?: string; color?: string }) =>
        apiFetch<Annotation>(`/books/${bookId}/annotations`, {
            method: 'POST',
            body: JSON.stringify(data),
        }),
        
    updateAnnotation: (annotationId: number, data: { note?: string; color?: string }) =>
        apiFetch<Annotation>(`/annotations/${annotationId}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        }),
        
    deleteAnnotation: (annotationId: number) =>
        apiFetch<{ message: string }>(`/annotations/${annotationId}`, { method: 'DELETE' }),
};
