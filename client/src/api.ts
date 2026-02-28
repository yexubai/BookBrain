/**
 * API client for BookBrain backend.
 */

const API_BASE = '/api';

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

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${API_BASE}${url}`, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'API error');
    }
    return res.json();
}

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

    getCoverUrl: (id: number) => `${API_BASE}/books/${id}/cover`,

    // Categories
    getCategories: () => apiFetch<Category[]>('/categories'),

    // Search
    search: (q: string, limit?: number) => {
        const qs = new URLSearchParams({ q });
        if (limit) qs.set('limit', String(limit));
        return apiFetch<SearchResponse>(`/search?${qs}`);
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
