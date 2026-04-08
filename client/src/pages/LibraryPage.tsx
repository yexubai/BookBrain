/**
 * LibraryPage — Main book listing page.
 *
 * Displays books in a paginated grid or list view with optional filtering
 * by category and search query.  The search query is debounced (400ms)
 * to avoid excessive API calls while the user is typing.
 *
 * Clicking a book card opens the BookDetail modal.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { api, Book, BookListResponse } from '../api'
import BookDetail from '../components/BookDetail'
import { FiGrid, FiList, FiBook } from 'react-icons/fi'

interface LibraryPageProps {
    selectedCategory: string | null  // Category filter from Sidebar (null = all)
    searchQuery: string              // Live search text from Topbar
}

/** Format file size in bytes to human-readable string (B / KB / MB). */
function formatSize(bytes: number): string {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

export default function LibraryPage({ selectedCategory, searchQuery }: LibraryPageProps) {
    const [data, setData] = useState<BookListResponse | null>(null)
    const [loading, setLoading] = useState(true)
    const [view, setView] = useState<'grid' | 'list'>('grid')  // Toggle between grid and list layout
    const [page, setPage] = useState(1)
    const [selectedBook, setSelectedBook] = useState<Book | null>(null)  // Book for the detail modal
    // Debounced query — delays API call by 400ms after user stops typing
    const [debouncedQuery, setDebouncedQuery] = useState(searchQuery)
    const pageSize = 20
    const abortRef = useRef<AbortController | null>(null)  // Cancel in-flight requests on re-fetch

    useEffect(() => {
        const timer = setTimeout(() => setDebouncedQuery(searchQuery), 400)
        return () => clearTimeout(timer)
    }, [searchQuery])

    useEffect(() => {
        setPage(1)
    }, [selectedCategory, debouncedQuery])

    const fetchBooks = useCallback(async () => {
        // Cancel any in-flight request before starting a new one
        if (abortRef.current) abortRef.current.abort()
        abortRef.current = new AbortController()
        setLoading(true)
        try {
            const result = await api.getBooks({
                page,
                page_size: pageSize,
                category: selectedCategory || undefined,
                q: debouncedQuery || undefined,
            })
            setData(result)
        } catch (e) {
            console.error('Failed to fetch books:', e)
        } finally {
            setLoading(false)
        }
    }, [page, selectedCategory, debouncedQuery])

    useEffect(() => {
        fetchBooks()
    }, [fetchBooks])

    // Show spinner only on first load; keep stale data visible during page changes
    if (loading && !data) {
        return <div className="loading"><div className="spinner" /></div>
    }

    const books = data?.books || []
    const total = data?.total || 0
    const totalPages = data?.total_pages || 0

    return (
        <div style={{ opacity: loading ? 0.6 : 1, transition: 'opacity 0.15s' }}>
            <div className="page-header">
                <div>
                    <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {selectedCategory || 'All Books'}
                        {selectedCategory && (
                            <button 
                                className="btn-icon" 
                                onClick={() => {
                                    // Triggering a custom event or using a prop to reset
                                    window.dispatchEvent(new CustomEvent('clear-category'));
                                }} 
                                title="Clear filter"
                                style={{ fontSize: '14px', opacity: 0.6 }}
                            >
                                ✕
                            </button>
                        )}
                    </h2>
                    <span className="page-meta">{total} book{total !== 1 ? 's' : ''}</span>
                </div>
                <div className="view-toggle">
                    <button
                        className={view === 'grid' ? 'active' : ''}
                        onClick={() => setView('grid')}
                        title="Grid view"
                    >
                        <FiGrid />
                    </button>
                    <button
                        className={view === 'list' ? 'active' : ''}
                        onClick={() => setView('list')}
                        title="List view"
                    >
                        <FiList />
                    </button>
                </div>
            </div>

            {books.length === 0 ? (
                <div className="empty-state">
                    <div className="empty-icon">📚</div>
                    <h3>No books found</h3>
                    <p>
                        {selectedCategory
                            ? `No books in "${selectedCategory}" category.`
                            : 'Import some ebooks to get started. Go to "Import Books" to scan your directories.'}
                    </p>
                </div>
            ) : view === 'grid' ? (
                <div className="book-grid">
                    {books.map(book => (
                        <div key={book.id} className="book-card" onClick={() => setSelectedBook(book)}>
                            <div className="cover-container">
                                {book.cover_path ? (
                                    <img src={api.getCoverUrl(book.id)} alt={book.title} loading="lazy" />
                                ) : (
                                    <div className="cover-placeholder">
                                        <FiBook className="placeholder-icon" />
                                        <span>{book.title}</span>
                                    </div>
                                )}
                            </div>
                            <div className="card-body">
                                <div className="card-title">{book.title}</div>
                                <div className="card-author">{book.author}</div>
                                <div className="card-meta">
                                    <span className="format-badge">{book.format}</span>
                                    <span className="card-category">{book.category}</span>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="book-list">
                    {books.map(book => (
                        <div key={book.id} className="book-list-item" onClick={() => setSelectedBook(book)}>
                            <div className="list-cover">
                                {book.cover_path ? (
                                    <img src={api.getCoverUrl(book.id)} alt={book.title} loading="lazy" />
                                ) : (
                                    <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)' }}>
                                        <FiBook />
                                    </div>
                                )}
                            </div>
                            <div className="list-info">
                                <div className="list-title">{book.title}</div>
                                <div className="list-author">{book.author}</div>
                            </div>
                            <div className="list-meta">
                                <span className="format-badge">{book.format}</span>
                                <span className="list-category">{book.category}</span>
                                <span className="list-size">{formatSize(book.file_size)}</span>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {totalPages > 1 && (
                <div className="pagination">
                    <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                        Previous
                    </button>
                    {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                        let p: number
                        if (totalPages <= 7) {
                            p = i + 1
                        } else if (page <= 4) {
                            p = i + 1
                        } else if (page >= totalPages - 3) {
                            p = totalPages - 6 + i
                        } else {
                            p = page - 3 + i
                        }
                        return (
                            <button
                                key={p}
                                className={page === p ? 'active' : ''}
                                onClick={() => setPage(p)}
                            >
                                {p}
                            </button>
                        )
                    })}
                    <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
                        Next
                    </button>
                </div>
            )}

            {selectedBook && (
                <BookDetail book={selectedBook} onClose={() => setSelectedBook(null)} />
            )}
        </div>
    )
}
