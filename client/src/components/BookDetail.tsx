import { api, Book } from '../api'
import { FiX } from 'react-icons/fi'

interface BookDetailProps {
    book: Book
    onClose: () => void
}

function formatSize(bytes: number): string {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

export default function BookDetail({ book, onClose }: BookDetailProps) {
    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content" onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <h2 style={{ fontSize: '18px', fontWeight: 600 }}>Book Details</h2>
                    <button className="modal-close" onClick={onClose} aria-label="Close">
                        <FiX />
                    </button>
                </div>
                <div className="modal-body">
                    <div className="modal-cover">
                        {book.cover_path ? (
                            <img src={api.getCoverUrl(book.id)} alt={book.title} />
                        ) : (
                            <div className="cover-placeholder" style={{ height: '260px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <span style={{ fontSize: '64px', opacity: 0.3 }}>📖</span>
                            </div>
                        )}
                    </div>
                    <div className="modal-details">
                        <div className="modal-title">{book.title}</div>
                        <div className="modal-author">{book.author}</div>

                        <div className="detail-grid">
                            <span className="detail-label">Format</span>
                            <span className="detail-value">{book.format.toUpperCase()}</span>

                            <span className="detail-label">Category</span>
                            <span className="detail-value">
                                {book.category}
                                {book.subcategory ? ` / ${book.subcategory}` : ''}
                            </span>

                            {book.publisher && (
                                <>
                                    <span className="detail-label">Publisher</span>
                                    <span className="detail-value">{book.publisher}</span>
                                </>
                            )}

                            {book.year && (
                                <>
                                    <span className="detail-label">Year</span>
                                    <span className="detail-value">{book.year}</span>
                                </>
                            )}

                            {book.isbn && (
                                <>
                                    <span className="detail-label">ISBN</span>
                                    <span className="detail-value">{book.isbn}</span>
                                </>
                            )}

                            {book.language && (
                                <>
                                    <span className="detail-label">Language</span>
                                    <span className="detail-value">{book.language}</span>
                                </>
                            )}

                            <span className="detail-label">File Size</span>
                            <span className="detail-value">{formatSize(book.file_size)}</span>

                            {book.page_count && (
                                <>
                                    <span className="detail-label">Pages</span>
                                    <span className="detail-value">{book.page_count}</span>
                                </>
                            )}

                            <span className="detail-label">OCR</span>
                            <span className="detail-value">{book.ocr_processed ? 'Yes' : 'No'}</span>

                            <span className="detail-label">Status</span>
                            <span className="detail-value">{book.processing_status}</span>
                        </div>

                        {book.summary && (
                            <div className="detail-summary">{book.summary}</div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}
