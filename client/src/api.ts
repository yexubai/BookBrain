/**
 * API client for BookBrain backend.
 *
 * Supports both local sidecar mode (localhost:8000) and remote NAS mode
 * (user-configured URL). The backend URL is stored in localStorage.
 */

const DEFAULT_BACKEND = 'http://localhost:8000';
const STORAGE_KEY = 'bookbrain_backend_url';

/** Get the configured backend URL. */
export function getBackendUrl(): string {
    if (typeof window !== 'undefined') {
        return localStorage.getItem(STORAGE_KEY) || DEFAULT_BACKEND;
    }
    return DEFAULT_BACKEND;
}

/** Set the backend URL. */
export function setBackendUrl(url: string) {
    const cleaned = url.replace(/\/+$/, ''); // Remove trailing slashes
    localStorage.setItem(STORAGE_KEY, cleaned);
}

/** Check if running inside Tauri desktop app. */
export function isTauri(): boolean {
    return !!(window as any).__TAURI_INTERNALS__;
}

function getApiBase(): string {
    // In web dev mode (Vite proxy), use relative path
    if (!isTauri() && window.location.port === '1420') {
        return '/api';
    }
    // Otherwise use configured backend URL
    return `${getBackendUrl()}/api`;
}

// ─── Types ──────────────────────────────────────────

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
}

export interface SearchResponse {
    query: string;
    results: SearchResult[];
    total: number;
}

export interface UnifiedSearchResult {
    book: Book;
    score: number;
    /** "keyword" = FTS5 title/author/filename match; "semantic" = vector similarity */
    source: 'keyword' | 'semantic';
    filename?: string;
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
    failed_files: number;
    current_file?: string;
    errors: string[];
    progress_percent: number;
}

export interface Settings {
    ebook_dirs: string;
    ocr_enabled: boolean;
    ocr_language: string;
    embedding_model: string;
    max_workers: number;
    data_dir: string;
}

export interface Stats {
    total_books: number;
    formats: Record<string, number>;
    category_count: number;
    total_size_bytes: number;
}

// ─── API Fetch ──────────────────────────────────────

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

/** Check if the backend is reachable. */
export async function checkBackendHealth(): Promise<boolean> {
    try {
        const url = getBackendUrl();
        const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
        return res.ok;
    } catch {
        return false;
    }
}

// ─── API Methods ────────────────────────────────────

export const api = {
    // Books
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

    getCoverUrl: (id: number) => `${getApiBase()}/books/${id}/cover`,

    getFileUrl: (id: number) => `${getApiBase()}/books/${id}/file`,

    // Categories
    getCategories: () => apiFetch<Category[]>('/categories'),

    // Search
    search: (q: string, limit?: number) => {
        const qs = new URLSearchParams({ q });
        if (limit) qs.set('limit', String(limit));
        return apiFetch<SearchResponse>(`/search?${qs}`);
    },

    searchUnified: (q: string, limit?: number) => {
        const qs = new URLSearchParams({ q });
        if (limit) qs.set('limit', String(limit));
        return apiFetch<UnifiedSearchResponse>(`/search/unified?${qs}`);
    },

    // Ingest
    triggerIngest: (directories?: string[]) =>
        apiFetch<IngestStatus>('/ingest', {
            method: 'POST',
            body: JSON.stringify({ directories }),
        }),

    getIngestStatus: () => apiFetch<IngestStatus>('/ingest/status'),

    // Settings
    getSettings: () => apiFetch<Settings>('/settings'),

    updateSettings: (data: Partial<Settings>) =>
        apiFetch<Settings>('/settings', {
            method: 'PUT',
            body: JSON.stringify(data),
        }),

    // Stats
    getStats: () => apiFetch<Stats>('/stats'),
};
