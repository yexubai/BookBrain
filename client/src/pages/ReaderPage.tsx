import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { api, Book, Annotation } from '../api'
import { FiArrowLeft, FiChevronLeft, FiChevronRight, FiZoomIn, FiZoomOut, FiMaximize, FiEdit3, FiCopy, FiTrash2, FiX } from 'react-icons/fi'
import * as pdfjsLib from 'pdfjs-dist'
import 'pdfjs-dist/web/pdf_viewer.css'

// Set worker to a more reliable local-ish path or at least handle errors
// In a real production app, this should be bundled or put in public/
pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${pdfjsLib.version}/build/pdf.worker.min.mjs`

// ─── Shared UI Components ───────────────────────────────────────

export const COLORS = [
    { name: 'yellow', hex: 'rgba(255, 235, 59, 0.4)' },
    { name: 'green', hex: 'rgba(76, 175, 80, 0.3)' },
    { name: 'blue', hex: 'rgba(33, 150, 243, 0.3)' },
    { name: 'purple', hex: 'rgba(156, 39, 176, 0.3)' },
    { name: 'red', hex: 'rgba(244, 67, 54, 0.3)' }
]

function ContextMenu({ 
    x, y, 
    onCopy, 
    onHighlight 
}: { 
    x: number; y: number; 
    onCopy: () => void; 
    onHighlight: (color: string) => void;
}) {
    return (
        <div className="context-menu" style={{ left: x, top: y, zIndex: 1000 }}>
            <button className="ctx-btn" onClick={onCopy}><FiCopy /> Copy</button>
            <div className="ctx-divider" />
            <div className="ctx-colors">
                {COLORS.map(c => (
                    <div 
                        key={c.name} 
                        className="color-circle" 
                        style={{ background: c.hex.replace(/0\.[0-9]\)/, '1)') }}
                        onClick={() => onHighlight(c.name)}
                        title={`Highlight ${c.name}`}
                    />
                ))}
            </div>
        </div>
    )
}

function NoteDialog({ 
    initialNote, 
    onSave, 
    onClose, 
    onDelete 
}: { 
    initialNote: string; 
    onSave: (note: string) => void; 
    onClose: () => void; 
    onDelete?: () => void 
}) {
    const [note, setNote] = useState(initialNote || "")
    return (
        <div className="modal-overlay" onClick={onClose} style={{ zIndex: 2000 }}>
            <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '400px' }}>
                <div className="modal-header">
                    <div className="modal-title" style={{ fontSize: '18px' }}>Edit Note</div>
                    <button className="modal-close" onClick={onClose}><FiX /></button>
                </div>
                <div className="modal-body" style={{ flexDirection: 'column' }}>
                    <textarea 
                        autoFocus
                        value={note}
                        onChange={e => setNote(e.target.value)}
                        placeholder="Add your note here..."
                        style={{ width: '100%', height: '120px', padding: '12px', background: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: '4px', color: 'var(--text-primary)', resize: 'none', fontFamily: 'inherit' }}
                    />
                    <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '16px' }}>
                        {onDelete && (
                            <button className="btn btn-secondary" onClick={onDelete} style={{ color: 'var(--error)', borderColor: 'var(--error)' }}>
                                <FiTrash2 /> Delete
                            </button>
                        )}
                        <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
                        <button className="btn btn-primary" onClick={() => onSave(note)}>Save Note</button>
                    </div>
                </div>
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

                let text = await res.text()
                if (['html', 'htm'].includes(book.format)) {
                    const parser = new DOMParser()
                    const doc = parser.parseFromString(text, 'text/html')
                    text = doc.body.innerText || doc.body.textContent || text
                } else if (['mobi', 'azw3'].includes(book.format)) {
                    text = text.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]/g, '')
                    text = text.replace(/<[^>]+>/g, ' ') 
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

// ─── PDF Reader Components ──────────────────────────────────────

function PdfPageCanvas({ 
    pdfDoc, 
    pageNum, 
    scale, 
    annotations, 
    onEditNote 
}: { 
    pdfDoc: any; 
    pageNum: number; 
    scale: number;
    annotations: Annotation[];
    onEditNote: (ann: Annotation) => void;
}) {
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const textLayerRef = useRef<HTMLDivElement>(null)
    const containerRef = useRef<HTMLDivElement>(null)
    const renderTaskRef = useRef<any>(null)
    const [visible, setVisible] = useState(false)

    useEffect(() => {
        const el = containerRef.current
        if (!el) return
        const observer = new IntersectionObserver(
            ([entry]) => setVisible(entry.isIntersecting),
            { rootMargin: '600px' }
        )
        observer.observe(el)
        return () => observer.disconnect()
    }, [])

    useEffect(() => {
        if (!visible || !pdfDoc || !canvasRef.current) return
        let cancelled = false
        const render = async () => {
            try {
                const page = await pdfDoc.getPage(pageNum)
                if (cancelled) return
                const viewport = page.getViewport({ scale })
                const canvas = canvasRef.current!
                const ctx = canvas.getContext('2d')!
                canvas.width = viewport.width
                canvas.height = viewport.height

                if (renderTaskRef.current) {
                    try { renderTaskRef.current.cancel() } catch { }
                }
                renderTaskRef.current = page.render({ canvasContext: ctx, viewport })
                await renderTaskRef.current.promise

                const textLayerDiv = textLayerRef.current!
                textLayerDiv.innerHTML = ''
                textLayerDiv.style.width = `${viewport.width}px`
                textLayerDiv.style.height = `${viewport.height}px`
                
                try {
                    const textContent = await page.getTextContent()
                    const textLayer = new pdfjsLib.TextLayer({
                        textContentSource: textContent,
                        container: textLayerDiv,
                        viewport: viewport
                    })
                    await textLayer.render()
                } catch (err) {
                    console.warn('TextLayer render error:', err)
                }
            } catch (e: any) {
                if (e.name !== 'RenderingCancelledException' && !cancelled) console.error('Render error:', e)
            }
        }
        render()
        return () => { cancelled = true }
    }, [pdfDoc, pageNum, scale, visible])

    return (
        <div ref={containerRef} className="pdf-page-wrapper" data-page={pageNum} style={{ position: 'relative' }}>
            <canvas ref={canvasRef} />
            <div ref={textLayerRef} className="textLayer" />
            
            {annotations.map(ann => {
                let rects: Array<{left: number, top: number, width: number, height: number}> = []
                try { rects = JSON.parse(ann.location).rects || [] } catch {}
                
                return (
                    <div key={ann.id} onClick={() => onEditNote(ann)} title={ann.note || "Add note"}>
                        {rects.map((rect, i) => {
                            const c = COLORS.find(c => c.name === ann.color) || COLORS[0]
                            return (
                                <div 
                                    key={i} 
                                    className="annotation-highlight"
                                    style={{
                                        left: rect.left, top: rect.top, width: rect.width, height: rect.height,
                                        background: c.hex
                                    }}
                                />
                            )
                        })}
                    </div>
                )
            })}
            
            <div className="pdf-page-number">Page {pageNum}</div>
        </div>
    )
}

function PdfReader({ bookId }: { bookId: number }) {
    const scrollContainerRef = useRef<HTMLDivElement>(null)
    const [pdfDoc, setPdfDoc] = useState<any>(null)
    const [totalPages, setTotalPages] = useState(0)
    const [currentPage, setCurrentPage] = useState(1)
    const [scale, setScale] = useState(1.5)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')

    useEffect(() => {
        const load = async () => {
            try {
                const url = api.getFileUrl(bookId)
                const doc = await pdfjsLib.getDocument(url).promise
                setPdfDoc(doc)
                setTotalPages(doc.numPages)
                setLoading(false)
            } catch (e: any) {
                console.error("PDF loading error:", e)
                setError(e.message || 'Failed to load PDF')
                setLoading(false)
            }
        }
        load()
    }, [bookId])

    useEffect(() => {
        const container = scrollContainerRef.current
        if (!container || !totalPages) return
        const onScroll = () => {
            const wrappers = container.querySelectorAll('.pdf-page-wrapper')
            const containerTop = container.scrollTop + container.clientHeight / 3
            for (let i = wrappers.length - 1; i >= 0; i--) {
                const el = wrappers[i] as HTMLElement
                if (el.offsetTop <= containerTop) {
                    setCurrentPage(i + 1)
                    break
                }
            }
        }
        container.addEventListener('scroll', onScroll, { passive: true })
        return () => container.removeEventListener('scroll', onScroll)
    }, [totalPages])

    useEffect(() => {
        const container = scrollContainerRef.current
        const handleKey = (e: KeyboardEvent) => {
            if (!container) return
            const scrollAmount = 200
            if (e.key === 'ArrowDown') { container.scrollBy({ top: scrollAmount, behavior: 'smooth' }); e.preventDefault() }
            else if (e.key === 'ArrowUp') { container.scrollBy({ top: -scrollAmount, behavior: 'smooth' }); e.preventDefault() }
            else if (e.key === 'PageDown' || e.key === ' ') { container.scrollBy({ top: container.clientHeight * 0.9, behavior: 'smooth' }); e.preventDefault() }
            else if (e.key === 'PageUp') { container.scrollBy({ top: -container.clientHeight * 0.9, behavior: 'smooth' }); e.preventDefault() }
            else if (e.key === 'ArrowRight') { goToPage(Math.min(totalPages, currentPage + 1)); e.preventDefault() }
            else if (e.key === 'ArrowLeft') { goToPage(Math.max(1, currentPage - 1)); e.preventDefault() }
            else if (e.key === '+' || e.key === '=') setScale(s => Math.min(3, s + 0.25))
            else if (e.key === '-') setScale(s => Math.max(0.5, s - 0.25))
            else if (e.key === 'Home') { container.scrollTo({ top: 0, behavior: 'smooth' }); e.preventDefault() }
            else if (e.key === 'End') { container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' }); e.preventDefault() }
        }
        window.addEventListener('keydown', handleKey)
        return () => window.removeEventListener('keydown', handleKey)
    }, [totalPages, currentPage])

    const goToPage = useCallback((pageNum: number) => {
        const container = scrollContainerRef.current
        if (!container) return
        const wrapper = container.querySelector(`[data-page="${pageNum}"]`) as HTMLElement
        if (wrapper) {
            wrapper.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }
    }, [])

    const [contextMenu, setContextMenu] = useState<{ x: number, y: number, text: string, page: number, rects: any[] } | null>(null)
    const [annotations, setAnnotations] = useState<Annotation[]>([])
    const [editingNote, setEditingNote] = useState<Annotation | null>(null)

    useEffect(() => {
        api.getAnnotations(bookId).then(setAnnotations).catch(console.warn)
    }, [bookId])

    const handleMouseUp = () => {
        const selection = window.getSelection()
        if (!selection || selection.isCollapsed) {
            setContextMenu(null)
            return
        }
        
        try {
            const range = selection.getRangeAt(0)
            const node = range.startContainer
            
            const wrapper = node.nodeType === 3 ? node.parentElement?.closest('.pdf-page-wrapper') : (node as Element).closest('.pdf-page-wrapper')
            if (!wrapper) return
            
            const pageNum = Number(wrapper.getAttribute('data-page'))
            const wrapperRect = wrapper.getBoundingClientRect()
            
            const text = selection.toString().trim()
            if (!text) return
            
            const clientRects = range.getClientRects()
            if (!clientRects.length) return
            
            const relativeRects = Array.from(clientRects).map(r => ({
                left: r.left - wrapperRect.left,
                top: r.top - wrapperRect.top,
                width: r.width,
                height: r.height
            }))
            
            const firstRect = clientRects[0]
            
            setContextMenu({ 
                x: firstRect.left + firstRect.width / 2, 
                y: firstRect.top, 
                text, 
                page: pageNum,
                rects: relativeRects
            })
        } catch(e) {
            console.error(e)
        }
    }

    const saveHighlight = async (color: string) => {
        if (!contextMenu) return
        try {
            const location = JSON.stringify({ page: contextMenu.page, rects: contextMenu.rects })
            const ann = await api.createAnnotation(bookId, {
                location,
                selected_text: contextMenu.text,
                color,
            })
            setAnnotations(prev => [...prev, ann])
            setContextMenu(null)
            window.getSelection()?.removeAllRanges()
        } catch (e) {
            console.error("Failed to save highlight", e)
        }
    }

    const copyText = async () => {
        if (!contextMenu) return
        try {
            await navigator.clipboard.writeText(contextMenu.text)
            setContextMenu(null)
            window.getSelection()?.removeAllRanges()
        } catch(e) {
            console.error('Failed to copy', e)
        }
    }

    if (loading) return <div className="loading"><div className="spinner" /></div>
    if (error) return <div className="empty-state"><h3>{error}</h3></div>

    const pages = Array.from({ length: totalPages }, (_, i) => i + 1)

    return (
        <div className="pdf-reader" onMouseUp={handleMouseUp}>
            <div className="reader-controls">
                <button className="btn-icon" onClick={() => goToPage(Math.max(1, currentPage - 1))} disabled={currentPage <= 1}>
                    <FiChevronLeft />
                </button>
                <span className="page-indicator">
                    <input
                        type="number"
                        value={currentPage}
                        onChange={e => { const p = Number(e.target.value); if (p >= 1 && p <= totalPages) goToPage(p) }}
                        min={1} max={totalPages}
                        style={{ width: '50px', textAlign: 'center' }}
                    />
                    / {totalPages}
                </span>
                <button className="btn-icon" onClick={() => goToPage(Math.min(totalPages, currentPage + 1))} disabled={currentPage >= totalPages}>
                    <FiChevronRight />
                </button>
                <div className="zoom-controls">
                    <button className="btn-icon" onClick={() => setScale(s => Math.max(0.5, s - 0.25))} title="Zoom out"><FiZoomOut /></button>
                    <span className="zoom-label">{Math.round(scale * 100)}%</span>
                    <button className="btn-icon" onClick={() => setScale(s => Math.min(3, s + 0.25))} title="Zoom in"><FiZoomIn /></button>
                    <button className="btn-icon" onClick={() => setScale(1.5)} title="Reset zoom"><FiMaximize /></button>
                </div>
            </div>
            <div className="canvas-container" ref={scrollContainerRef} tabIndex={0} style={{ overflowY: 'auto', height: '100%' }}>
                {pages.map(pageNum => (
                    <PdfPageCanvas 
                        key={pageNum} 
                        pdfDoc={pdfDoc} 
                        pageNum={pageNum} 
                        scale={scale} 
                        annotations={annotations.filter(a => {
                            try { return JSON.parse(a.location).page === pageNum } catch { return false }
                        })}
                        onEditNote={setEditingNote}
                    />
                ))}
            </div>

            {contextMenu && (
                <ContextMenu 
                    x={contextMenu.x} 
                    y={contextMenu.y} 
                    onCopy={copyText}
                    onHighlight={saveHighlight}
                />
            )}

            {editingNote && (
                <NoteDialog
                    initialNote={editingNote.note}
                    onClose={() => setEditingNote(null)}
                    onDelete={async () => {
                        await api.deleteAnnotation(editingNote.id)
                        setAnnotations(prev => prev.filter(a => a.id !== editingNote.id))
                        setEditingNote(null)
                    }}
                    onSave={async (note) => {
                        const updated = await api.updateAnnotation(editingNote.id, { note })
                        setAnnotations(prev => prev.map(a => a.id === updated.id ? updated : a))
                        setEditingNote(null)
                    }}
                />
            )}
        </div>
    )
}

// ─── EPUB Reader ────────────────────────────────────────────────

function EpubReader({ bookId }: { bookId: number }) {
    const containerRef = useRef<HTMLDivElement>(null)
    const renditionRef = useRef<any>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [tocItems, setTocItems] = useState<Array<{ label: string; href: string }>>([])
    const [showToc, setShowToc] = useState(false)
    
    const [contextMenu, setContextMenu] = useState<{ x: number, y: number, text: string, cfiRange: string } | null>(null)
    const [annotations, setAnnotations] = useState<Annotation[]>([])
    const [editingNote, setEditingNote] = useState<Annotation | null>(null)

    useEffect(() => {
        let book: any = null
        const init = async () => {
            try {
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
                        '::selection': { 'background': 'rgba(88, 166, 255, 0.4) !important' }
                    })

                    api.getAnnotations(bookId).then(anns => {
                        setAnnotations(anns)
                        anns.forEach(ann => {
                            try {
                                const loc = JSON.parse(ann.location)
                                if (loc.cfi) {
                                    const c = COLORS.find(c => c.name === ann.color) || COLORS[0]
                                    rendition.annotations.highlight(loc.cfi, {}, (e: any) => {
                                        setEditingNote(ann)
                                    }, '', { fill: c.hex, 'fill-opacity': '1' })
                                }
                            } catch {}
                        })
                    }).catch(console.warn)

                    rendition.on('selected', (cfiRange: string, contents: any) => {
                        const range = rendition.getRange(cfiRange)
                        if (!range) return
                        const rect = range.getBoundingClientRect()
                        const text = range.toString().trim()
                        if (text) {
                            const containerRect = containerRef.current?.getBoundingClientRect()
                            let x, y;
                            if (containerRect) {
                                x = rect.left + rect.width / 2 + containerRect.left
                                y = rect.top + containerRect.top
                            } else {
                                x = rect.left + rect.width / 2
                                y = rect.top
                            }
                            setContextMenu({ x, y, text, cfiRange })
                        }
                    })

                    rendition.on('click', () => setContextMenu(null))
                    rendition.on('relocated', () => setContextMenu(null))
                    await rendition.display()
                    setLoading(false)
                }
            } catch (e: any) {
                console.error("EPUB loading error:", e)
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

    useEffect(() => {
        const handleKey = (e: KeyboardEvent) => {
            if (!renditionRef.current) return
            if (e.key === 'ArrowLeft' || e.key === 'PageUp') renditionRef.current.prev()
            else if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') renditionRef.current.next()
        }
        window.addEventListener('keydown', handleKey)
        return () => window.removeEventListener('keydown', handleKey)
    }, [])

    if (loading) return <div className="loading"><div className="spinner" /></div>
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

            {contextMenu && (
                <ContextMenu 
                    x={contextMenu.x} 
                    y={contextMenu.y} 
                    onCopy={async () => {
                        try {
                            await navigator.clipboard.writeText(contextMenu.text)
                            setContextMenu(null)
                            renditionRef.current?.getContents()?.forEach((c: any) => c.window.getSelection()?.removeAllRanges())
                        } catch(e) { console.error('Failed to copy', e) }
                    }}
                    onHighlight={async (color) => {
                        if (!contextMenu) return
                        try {
                            const location = JSON.stringify({ cfi: contextMenu.cfiRange })
                            const ann = await api.createAnnotation(bookId, {
                                location,
                                selected_text: contextMenu.text,
                                color,
                            })
                            setAnnotations(prev => [...prev, ann])
                            setContextMenu(null)
                            renditionRef.current?.getContents()?.forEach((c: any) => c.window.getSelection()?.removeAllRanges())

                            const cData = COLORS.find(c => c.name === color) || COLORS[0]
                            renditionRef.current?.annotations.highlight(contextMenu.cfiRange, {}, (e: any) => {
                                setEditingNote(ann)
                            }, '', { fill: cData.hex, 'fill-opacity': '1' })
                        } catch(e) { console.error("Failed to save highlight", e) }
                    }}
                />
            )}

            {editingNote && (
                <NoteDialog
                    initialNote={editingNote.note}
                    onClose={() => setEditingNote(null)}
                    onDelete={async () => {
                        await api.deleteAnnotation(editingNote.id)
                        try {
                            const loc = JSON.parse(editingNote.location)
                            if (loc.cfi) {
                                renditionRef.current?.annotations.remove(loc.cfi, 'highlight')
                            }
                        } catch {}
                        setAnnotations(prev => prev.filter(a => a.id !== editingNote.id))
                        setEditingNote(null)
                    }}
                    onSave={async (note) => {
                        const updated = await api.updateAnnotation(editingNote.id, { note })
                        setAnnotations(prev => prev.map(a => a.id === updated.id ? updated : a))
                        setEditingNote(null)
                    }}
                />
            )}
        </div>
    )
}

// ─── Main Reader Page ───────────────────────────────────────────

export default function ReaderPage() {
    const [params] = useSearchParams()
    const navigate = useNavigate()
    const bookId = Number(params.get('id'))
    const [book, setBook] = useState<Book | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')

    useEffect(() => {
        if (!bookId) { setError('No book ID provided'); setLoading(false); return }
        api.getBook(bookId)
            .then(b => {
                setBook(b);
                setLoading(false);
            })
            .catch(e => {
                console.error("ReaderPage loading error:", e);
                setError(e.message || 'Failed to fetch book metadata');
                setLoading(false);
            })
    }, [bookId])

    if (loading) return <div className="loading"><div className="spinner" /></div>
    
    // Add protective boundary here
    if (error || !book) {
        return (
            <div className="empty-state">
                <h3>Viewer Error</h3>
                <p style={{ color: 'var(--error)', marginTop: '8px' }}>{error || 'Unknown error occurred while loading book.'}</p>
                <button className="btn btn-secondary" onClick={() => navigate(-1)} style={{ marginTop: '20px' }}>
                    Go Back
                </button>
            </div>
        )
    }

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
