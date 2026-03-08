import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { api, Book } from '../api'
import { FiArrowLeft, FiChevronLeft, FiChevronRight, FiZoomIn, FiZoomOut, FiMaximize } from 'react-icons/fi'
import * as pdfjsLib from 'pdfjs-dist'

// Set worker
pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${pdfjsLib.version}/build/pdf.worker.min.mjs`

export default function ReaderPage() {
    const [params] = useSearchParams()
    const navigate = useNavigate()
    const bookId = Number(params.get('id'))
    const [book, setBook] = useState<Book | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')

    useEffect(() => {
        if (!bookId) { setError('No book ID'); setLoading(false); return }
        api.getBook(bookId).then(setBook).catch(e => setError(e.message)).finally(() => setLoading(false))
    }, [bookId])

    if (loading) return <div className="loading"><div className="spinner" /></div>
    if (error || !book) return <div className="empty-state"><h3>{error || 'Book not found'}</h3></div>

    return (
        <div className="reader-page">
            <div className="reader-toolbar">
                <button className="btn-icon" onClick={() => navigate(-1)} title="Back">
                    <FiArrowLeft />
                </button>
                <span className="reader-title">{book.title}</span>
            </div>
            <div className="reader-content">
                {book.format === 'pdf' ? (
                    <PdfReader bookId={bookId} />
                ) : book.format === 'epub' ? (
                    <EpubReader bookId={bookId} />
                ) : ['txt', 'html', 'htm', 'mobi', 'azw3'].includes(book.format) ? (
                    <TextReader book={book} />
                ) : (
                    <div className="empty-state"><h3>Unsupported reading format: {book.format}</h3></div>
                )}
            </div>
        </div>
    )
}

// ─── Text/HTML/Basic Reader ─────────────────────────────────────

function TextReader({ book }: { book: Book }) {
    const [content, setContent] = useState('')
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [fontSize, setFontSize] = useState(16)

    useEffect(() => {
        const load = async () => {
            try {
                const url = api.getFileUrl(book.id)
                const res = await fetch(url)
                if (!res.ok) throw new Error('Failed to load file')

                // For HTML, attempt to strip head/styles
                let text = await res.text()
                if (['html', 'htm'].includes(book.format)) {
                    const parser = new DOMParser()
                    const doc = parser.parseFromString(text, 'text/html')
                    text = doc.body.innerText || doc.body.textContent || text
                } else if (['mobi', 'azw3'].includes(book.format)) {
                    // Very crude raw text extraction for mobi/azw3 in browser
                    // Just removes obvious binary garbage
                    text = text.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]/g, '')
                    text = text.replace(/<[^>]+>/g, ' ') // Strip tags
                }

                setContent(text)
                setLoading(false)
            } catch (e: any) {
                setError(e.message || 'Error loading file')
                setLoading(false)
            }
        }
        load()
    }, [book])

    if (loading) return <div className="loading"><div className="spinner" /></div>
    if (error) return <div className="empty-state"><h3>{error}</h3></div>

    return (
        <div className="text-reader" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <div className="reader-controls">
                <button className="btn-icon" onClick={() => setFontSize(s => Math.max(12, s - 2))} title="Decrease font size">
                    <FiZoomOut />
                </button>
                <span className="zoom-label">{fontSize}px</span>
                <button className="btn-icon" onClick={() => setFontSize(s => Math.min(32, s + 2))} title="Increase font size">
                    <FiZoomIn />
                </button>
            </div>

            <div className="text-viewer" style={{
                flex: 1,
                overflowY: 'auto',
                padding: '40px 10%',
                background: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                fontSize: `${fontSize}px`,
                lineHeight: 1.8,
                whiteSpace: 'pre-wrap',
                fontFamily: 'var(--font)'
            }}>
                {content}
            </div>
        </div>
    )
}

// ─── PDF Reader ─────────────────────────────────────────────────

function PdfReader({ bookId }: { bookId: number }) {
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const [pdfDoc, setPdfDoc] = useState<any>(null)
    const [currentPage, setCurrentPage] = useState(1)
    const [totalPages, setTotalPages] = useState(0)
    const [scale, setScale] = useState(1.5)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const renderTaskRef = useRef<any>(null)

    // Load PDF
    useEffect(() => {
        const load = async () => {
            try {
                const url = api.getFileUrl(bookId)
                const doc = await pdfjsLib.getDocument(url).promise
                setPdfDoc(doc)
                setTotalPages(doc.numPages)
                setLoading(false)
            } catch (e: any) {
                setError(e.message || 'Failed to load PDF')
                setLoading(false)
            }
        }
        load()
    }, [bookId])

    // Render page
    const renderPage = useCallback(async () => {
        if (!pdfDoc || !canvasRef.current) return
        try {
            const page = await pdfDoc.getPage(currentPage)
            const viewport = page.getViewport({ scale })
            const canvas = canvasRef.current
            const ctx = canvas.getContext('2d')!
            canvas.width = viewport.width
            canvas.height = viewport.height

            if (renderTaskRef.current) {
                try { renderTaskRef.current.cancel() } catch { }
            }

            renderTaskRef.current = page.render({ canvasContext: ctx, viewport })
            await renderTaskRef.current.promise
        } catch (e: any) {
            if (e.name !== 'RenderingCancelledException') console.error('Render error:', e)
        }
    }, [pdfDoc, currentPage, scale])

    useEffect(() => { renderPage() }, [renderPage])

    // Keyboard
    useEffect(() => {
        const handleKey = (e: KeyboardEvent) => {
            if (e.key === 'ArrowLeft' || e.key === 'PageUp') setCurrentPage(p => Math.max(1, p - 1))
            else if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') setCurrentPage(p => Math.min(totalPages, p + 1))
            else if (e.key === '+' || e.key === '=') setScale(s => Math.min(3, s + 0.25))
            else if (e.key === '-') setScale(s => Math.max(0.5, s - 0.25))
        }
        window.addEventListener('keydown', handleKey)
        return () => window.removeEventListener('keydown', handleKey)
    }, [totalPages])

    if (loading) return <div className="loading"><div className="spinner" /></div>
    if (error) return <div className="empty-state"><h3>{error}</h3></div>

    return (
        <div className="pdf-reader">
            <div className="reader-controls">
                <button className="btn-icon" onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage <= 1}>
                    <FiChevronLeft />
                </button>
                <span className="page-indicator">
                    <input
                        type="number"
                        value={currentPage}
                        onChange={e => { const p = Number(e.target.value); if (p >= 1 && p <= totalPages) setCurrentPage(p) }}
                        min={1} max={totalPages}
                        style={{ width: '50px', textAlign: 'center' }}
                    />
                    / {totalPages}
                </span>
                <button className="btn-icon" onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))} disabled={currentPage >= totalPages}>
                    <FiChevronRight />
                </button>
                <div className="zoom-controls">
                    <button className="btn-icon" onClick={() => setScale(s => Math.max(0.5, s - 0.25))} title="Zoom out"><FiZoomOut /></button>
                    <span className="zoom-label">{Math.round(scale * 100)}%</span>
                    <button className="btn-icon" onClick={() => setScale(s => Math.min(3, s + 0.25))} title="Zoom in"><FiZoomIn /></button>
                    <button className="btn-icon" onClick={() => setScale(1.5)} title="Reset zoom"><FiMaximize /></button>
                </div>
            </div>
            <div className="canvas-container">
                <canvas ref={canvasRef} />
            </div>
        </div>
    )
}

// ─── EPUB Reader (using iframe-based approach) ──────────────────

function EpubReader({ bookId }: { bookId: number }) {
    const containerRef = useRef<HTMLDivElement>(null)
    const renditionRef = useRef<any>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [tocItems, setTocItems] = useState<Array<{ label: string; href: string }>>([])
    const [showToc, setShowToc] = useState(false)

    useEffect(() => {
        let book: any = null

        const init = async () => {
            try {
                // Load epub.js via dynamic script tag
                if (!(window as any).ePub) {
                    await new Promise<void>((resolve, reject) => {
                        const s = document.createElement('script')
                        s.src = 'https://cdn.jsdelivr.net/npm/epubjs@0.3.93/dist/epub.min.js'
                        s.onload = () => resolve()
                        s.onerror = () => reject(new Error('Failed to load epub.js'))
                        document.head.appendChild(s)
                    })
                }

                const ePub = (window as any).ePub
                const url = api.getFileUrl(bookId)
                book = ePub(url)

                await book.ready

                // TOC
                const nav = await book.loaded.navigation
                if (nav?.toc) {
                    setTocItems(nav.toc.map((t: any) => ({ label: t.label.trim(), href: t.href })))
                }

                if (containerRef.current) {
                    const rendition = book.renderTo(containerRef.current, {
                        width: '100%',
                        height: '100%',
                        spread: 'none',
                        flow: 'paginated',
                    })
                    renditionRef.current = rendition

                    // Dark theme
                    rendition.themes.default({
                        body: {
                            color: '#e6edf3 !important',
                            'background-color': '#0d1117 !important',
                            'font-family': '"Inter", "Noto Sans SC", sans-serif !important',
                            'line-height': '1.8 !important',
                            padding: '20px 40px !important',
                        },
                        'p, div, span, li': { color: '#e6edf3 !important' },
                        'h1,h2,h3,h4,h5,h6': { color: '#fff !important' },
                        a: { color: '#58a6ff !important' },
                        img: { 'max-width': '100% !important' },
                    })

                    rendition.on('relocated', () => { })
                    await rendition.display()
                    setLoading(false)
                }
            } catch (e: any) {
                setError(e.message || 'Failed to load EPUB')
                setLoading(false)
            }
        }

        init()

        return () => {
            if (renditionRef.current) try { renditionRef.current.destroy() } catch { }
            if (book) try { book.destroy() } catch { }
        }
    }, [bookId])

    // Keys
    useEffect(() => {
        const handleKey = (e: KeyboardEvent) => {
            if (!renditionRef.current) return
            if (e.key === 'ArrowLeft' || e.key === 'PageUp') renditionRef.current.prev()
            else if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') renditionRef.current.next()
        }
        window.addEventListener('keydown', handleKey)
        return () => window.removeEventListener('keydown', handleKey)
    }, [])

    if (error) return <div className="empty-state"><h3>{error}</h3></div>

    return (
        <div className="epub-reader">
            <div className="reader-controls">
                <button className="btn-icon" onClick={() => renditionRef.current?.prev()} title="Previous">
                    <FiChevronLeft />
                </button>
                <button
                    className="btn-secondary"
                    onClick={() => setShowToc(!showToc)}
                    style={{ fontSize: '12px', padding: '4px 12px' }}
                >
                    Table of Contents
                </button>
                <button className="btn-icon" onClick={() => renditionRef.current?.next()} title="Next">
                    <FiChevronRight />
                </button>
            </div>

            {showToc && tocItems.length > 0 && (
                <div className="epub-toc">
                    {tocItems.map((item, i) => (
                        <div key={i} className="toc-item" onClick={() => { renditionRef.current?.display(item.href); setShowToc(false) }}>
                            {item.label}
                        </div>
                    ))}
                </div>
            )}

            <div ref={containerRef} className="epub-viewer" style={{ opacity: loading ? 0 : 1 }} />
            {loading && <div className="loading"><div className="spinner" /></div>}
        </div>
    )
}
