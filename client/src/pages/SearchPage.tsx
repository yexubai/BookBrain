import { useState, useEffect } from 'react'
import { api, Book, UnifiedSearchResult } from '../api'
import BookDetail from '../components/BookDetail'
import { FiSearch, FiBook, FiTag, FiCpu } from 'react-icons/fi'

interface SearchPageProps {
    query: string
}

export default function SearchPage({ query }: SearchPageProps) {
    const [results, setResults] = useState<UnifiedSearchResult[]>([])
    const [keywordCount, setKeywordCount] = useState(0)
    const [semanticCount, setSemanticCount] = useState(0)
    const [loading, setLoading] = useState(false)
    const [searched, setSearched] = useState(false)
    const [selectedBook, setSelectedBook] = useState<Book | null>(null)

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
                    {results.map(({ book, score, source, filename, context }) => (
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
                                {filename && filename !== book.title && (
                                    <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                        <span style={{ opacity: 0.7 }}>📄</span> {filename}
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
                            </div>
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
