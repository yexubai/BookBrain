/**
 * SearchPage — Unified search results page.
 *
 * Calls the `/api/search/unified` endpoint which combines FTS5 keyword
 * matching and FAISS semantic search.  Results show source badges
 * ("Keyword" / "Semantic"), relevance scores, matched text snippets,
 * and page-level jump-to-read links.
 *
 * Search is debounced by 500ms to avoid hammering the backend while typing.
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, Book, UnifiedSearchResult } from '../api'
import BookDetail from '../components/BookDetail'
import { FiSearch, FiBook, FiTag, FiCpu, FiBookOpen, FiInfo } from 'react-icons/fi'

interface SearchPageProps {
    query: string  // Current search text from the Topbar input
}

export default function SearchPage({ query }: SearchPageProps) {
    const navigate = useNavigate()
    const [results, setResults] = useState<UnifiedSearchResult[]>([])
    const [keywordCount, setKeywordCount] = useState(0)    // Results from FTS5
    const [semanticCount, setSemanticCount] = useState(0)  // Results from FAISS
    const [loading, setLoading] = useState(false)
    const [searched, setSearched] = useState(false)        // True after first search attempt
    const [selectedBook, setSelectedBook] = useState<Book | null>(null)
    const [selectedPage, setSelectedPage] = useState<number | undefined>(undefined)
    const [selectedLocation, setSelectedLocation] = useState<string | undefined>(undefined)

    /** Navigate to the reader, optionally jumping to a specific page/location. */
    const openReader = (book: Book, pageNumber?: number, locationTag?: string) => {
        let url = `/reader?id=${book.id}`
        if (pageNumber) url += `&page=${pageNumber}`
        if (locationTag) url += `&location=${encodeURIComponent(locationTag)}`
        navigate(url)
    }

    // Debounced search: waits 500ms after the user stops typing before firing the API call.
    // The cleanup function cancels the timer if the query changes before the timeout.
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
                const res = await api.searchUnified(query)
                setResults(res.results)
                setKeywordCount(res.keyword_count)
                setSemanticCount(res.semantic_count)
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
                    <h2>Search</h2>
                    <span className="page-meta">
                        {searched
                            ? results.length === 0
                                ? `No results for "${query}"`
                                : `${results.length} result${results.length !== 1 ? 's' : ''} — ${keywordCount} keyword, ${semanticCount} semantic`
                            : 'Enter a query to search by title, author, filename, or content meaning'}
                    </span>
                </div>
            </div>

            {loading ? (
                <div className="loading"><div className="spinner" /></div>
            ) : !searched ? (
                <div className="empty-state">
                    <FiSearch className="empty-icon" />
                    <h3>Search your library</h3>
                    <p>Searches by title, author, filename and content — supports partial matches and semantic understanding.</p>
                    <div style={{ marginTop: '16px', display: 'flex', gap: '24px', justifyContent: 'center', fontSize: '13px', color: 'var(--text-tertiary)' }}>
                        <span><FiTag style={{ marginRight: '4px', verticalAlign: 'middle' }} />Keyword match</span>
                        <span><FiCpu style={{ marginRight: '4px', verticalAlign: 'middle' }} />Semantic match</span>
                    </div>
                </div>
            ) : results.length === 0 ? (
                <div className="empty-state">
                    <div className="empty-icon">🔍</div>
                    <h3>No results found</h3>
                    <p>Try different search terms or import more books.</p>
                </div>
            ) : (
                <div className="search-results">
                    {results.map((result) => {
                        const { book, score, source, filename, context, page_number, location_tag } = result
                        return (
                        <div key={`${source}-${book.id}-${page_number || location_tag || Math.random()}`} className="search-result-item" onClick={() => openReader(book, page_number, location_tag)}>
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
                                {filename && filename !== book.title && (
                                    <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                        <span style={{ opacity: 0.7 }}>📄</span> {filename}
                                    </div>
                                )}
                                {page_number && (
                                    <div style={{ fontSize: '11px', color: 'var(--accent)', marginTop: '2px', fontWeight: 600 }}>
                                        <FiBookOpen style={{ marginRight: '4px', verticalAlign: 'middle' }} /> Jump to Page {page_number}
                                    </div>
                                )}
                                <div className="result-summary">{book.summary || 'No summary available'}</div>
                                {context && (
                                    <div className="result-context">
                                        <span style={{ fontSize: '10px', color: 'var(--accent)', fontWeight: 'bold', marginRight: '6px', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
                                            Matched text
                                        </span>
                                        <div
                                            style={{ display: 'inline', fontSize: '12.5px', color: 'var(--text-secondary)', lineHeight: '1.5' }}
                                            dangerouslySetInnerHTML={{ __html: context }}
                                        />
                                    </div>
                                )}
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '6px', minWidth: '80px' }}>
                                <div className="result-score">{(score * 100).toFixed(0)}%</div>
                                <div style={{
                                    fontSize: '10px',
                                    padding: '2px 6px',
                                    borderRadius: '4px',
                                    background: source === 'keyword' ? 'var(--accent-muted, rgba(88,166,255,0.15))' : 'rgba(63,185,80,0.15)',
                                    color: source === 'keyword' ? 'var(--accent, #58a6ff)' : '#3fb950',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '3px',
                                }}>
                                    {source === 'keyword'
                                        ? <><FiTag size={9} /> Keyword</>
                                        : <><FiCpu size={9} /> Semantic</>}
                                </div>
                                <button
                                    className="btn-icon"
                                    style={{ padding: '4px', fontSize: '14px' }}
                                    title="Book details"
                                    onClick={(e) => {
                                        e.stopPropagation()
                                        setSelectedBook(book)
                                        setSelectedPage(page_number)
                                        setSelectedLocation(location_tag)
                                    }}
                                >
                                    <FiInfo />
                                </button>
                            </div>
                        </div>
                        )
                    })}
                </div>
            )}

            {selectedBook && (
                <BookDetail 
                    book={selectedBook} 
                    pageNumber={selectedPage} 
                    locationTag={selectedLocation} 
                    onClose={() => {
                        setSelectedBook(null)
                        setSelectedPage(undefined)
                        setSelectedLocation(undefined)
                    }} 
                />
            )}
        </div>
    )
}
