import { useState, useEffect } from 'react'
import { api, SearchResult } from '../api'
import BookDetail from '../components/BookDetail'
import { FiSearch, FiBook } from 'react-icons/fi'

interface SearchPageProps {
    query: string
}

export default function SearchPage({ query }: SearchPageProps) {
    const [results, setResults] = useState<SearchResult[]>([])
    const [loading, setLoading] = useState(false)
    const [searched, setSearched] = useState(false)
    const [selectedBook, setSelectedBook] = useState<any>(null)

    useEffect(() => {
        if (!query.trim()) {
            setResults([])
            setSearched(false)
            return
        }

        const timer = setTimeout(async () => {
            setLoading(true)
            setSearched(true)
            try {
                const res = await api.search(query)
                setResults(res.results)
            } catch (e) {
                console.error('Search failed:', e)
                setResults([])
            } finally {
                setLoading(false)
            }
        }, 500)

        return () => clearTimeout(timer)
    }, [query])

    return (
        <div>
            <div className="page-header">
                <div>
                    <h2>Semantic Search</h2>
                    <span className="page-meta">
                        {searched ? `${results.length} result${results.length !== 1 ? 's' : ''} for "${query}"` : 'Enter a query to search by content'}
                    </span>
                </div>
            </div>

            {loading ? (
                <div className="loading"><div className="spinner" /></div>
            ) : !searched ? (
                <div className="empty-state">
                    <FiSearch className="empty-icon" />
                    <h3>Semantic Search</h3>
                    <p>Type a query in the search bar above to find books by content meaning, not just keywords.</p>
                </div>
            ) : results.length === 0 ? (
                <div className="empty-state">
                    <div className="empty-icon">🔍</div>
                    <h3>No results found</h3>
                    <p>Try different search terms or import more books to improve results.</p>
                </div>
            ) : (
                <div className="search-results">
                    {results.map(({ book, score }) => (
                        <div key={book.id} className="search-result-item" onClick={() => setSelectedBook(book)}>
                            <div className="result-cover">
                                {book.cover_path ? (
                                    <img src={api.getCoverUrl(book.id)} alt={book.title} loading="lazy" />
                                ) : (
                                    <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)' }}>
                                        <FiBook />
                                    </div>
                                )}
                            </div>
                            <div className="result-info">
                                <div className="result-title">{book.title}</div>
                                <div className="result-author">{book.author}</div>
                                <div className="result-summary">{book.summary || 'No summary available'}</div>
                            </div>
                            <div className="result-score">{(score * 100).toFixed(0)}%</div>
                        </div>
                    ))}
                </div>
            )}

            {selectedBook && (
                <BookDetail book={selectedBook} onClose={() => setSelectedBook(null)} />
            )}
        </div>
    )
}
