import { useState, useEffect, useRef } from 'react'
import { api, IngestStatus, Stats } from '../api'
import { FiUploadCloud, FiCheckCircle, FiAlertCircle } from 'react-icons/fi'

export default function IngestPage() {
    const [status, setStatus] = useState<IngestStatus | null>(null)
    const [stats, setStats] = useState<Stats | null>(null)
    const [dirs, setDirs] = useState('')
    const [loading, setLoading] = useState(false)
    const [toast, setToast] = useState<{ type: string; msg: string } | null>(null)
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

    useEffect(() => {
        api.getIngestStatus().then(setStatus).catch(() => { })
        api.getStats().then(setStats).catch(() => { })
        return () => { if (pollRef.current) clearInterval(pollRef.current) }
    }, [])

    const startIngest = async () => {
        setLoading(true)
        try {
            const directories = dirs.split(',').map(d => d.trim()).filter(Boolean)
            const res = await api.triggerIngest(directories.length ? directories : undefined)
            setStatus(res)

            // Poll for updates
            pollRef.current = setInterval(async () => {
                try {
                    const s = await api.getIngestStatus()
                    setStatus(s)
                    if (!s.is_running) {
                        if (pollRef.current) clearInterval(pollRef.current)
                        api.getStats().then(setStats)
                        setToast({ type: 'success', msg: `Processing complete! ${s.processed_files} books imported.` })
                        setTimeout(() => setToast(null), 5000)
                    }
                } catch (e) { /* ignore poll errors */ }
            }, 2000)
        } catch (e: any) {
            setToast({ type: 'error', msg: e.message || 'Failed to start import' })
            setTimeout(() => setToast(null), 5000)
        } finally {
            setLoading(false)
        }
    }

    const formatSize = (bytes: number) => {
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' KB'
        if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
        return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
    }

    return (
        <div>
            <div className="page-header">
                <div>
                    <h2>Import Books</h2>
                    <span className="page-meta">Scan directories and process ebooks</span>
                </div>
            </div>

            {/* Stats */}
            {stats && (
                <div className="ingest-stats" style={{ marginBottom: '24px' }}>
                    <div className="stat-card">
                        <div className="stat-value">{stats.total_books}</div>
                        <div className="stat-label">Total Books</div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-value">{stats.category_count}</div>
                        <div className="stat-label">Categories</div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-value">
                            {Object.entries(stats.formats).map(([f, c]) => `${f.toUpperCase()}: ${c}`).join(', ') || '—'}
                        </div>
                        <div className="stat-label">By Format</div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-value">{formatSize(stats.total_size_bytes)}</div>
                        <div className="stat-label">Total Size</div>
                    </div>
                </div>
            )}

            {/* Import */}
            <div className="ingest-panel">
                <h3 style={{ marginBottom: '16px', fontSize: '16px' }}>
                    <FiUploadCloud style={{ marginRight: '8px', verticalAlign: 'middle' }} />
                    Start Import
                </h3>

                <div className="setting-row" style={{ border: 'none' }}>
                    <div className="setting-label">
                        <div className="label-text">Directories</div>
                        <div className="label-desc">Comma-separated paths to scan. Leave empty to use configured directories.</div>
                    </div>
                    <div className="setting-control">
                        <input
                            type="text"
                            value={dirs}
                            onChange={e => setDirs(e.target.value)}
                            placeholder="e.g., /path/to/ebooks, /another/path"
                            disabled={status?.is_running}
                        />
                    </div>
                </div>

                <button
                    className="btn btn-primary"
                    onClick={startIngest}
                    disabled={loading || status?.is_running}
                    style={{ marginTop: '12px' }}
                >
                    {status?.is_running ? 'Processing...' : 'Start Scan'}
                </button>

                {/* Progress */}
                {status?.is_running && (
                    <div style={{ marginTop: '20px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                            <span>{status.current_file || 'Scanning...'}</span>
                            <span>{status.progress_percent.toFixed(0)}%</span>
                        </div>
                        <div className="progress-bar-container">
                            <div className="progress-bar" style={{ width: `${status.progress_percent}%` }} />
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginTop: '8px' }}>
                            {status.processed_files} / {status.total_files} files processed
                            {status.failed_files > 0 && `, ${status.failed_files} failed`}
                        </div>
                    </div>
                )}

                {/* Errors */}
                {status && status.errors.length > 0 && (
                    <div style={{ marginTop: '16px' }}>
                        <div style={{ fontSize: '13px', color: 'var(--error)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <FiAlertCircle /> {status.errors.length} error{status.errors.length > 1 ? 's' : ''}
                        </div>
                        <div style={{ maxHeight: '120px', overflow: 'auto', fontSize: '12px', color: 'var(--text-tertiary)', background: 'var(--bg-primary)', padding: '12px', borderRadius: 'var(--radius-sm)' }}>
                            {status.errors.map((err, i) => (
                                <div key={i}>{err}</div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Complete */}
                {status && !status.is_running && status.processed_files > 0 && (
                    <div style={{ marginTop: '16px', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--success)', fontSize: '14px' }}>
                        <FiCheckCircle />
                        Import complete: {status.processed_files} books processed
                    </div>
                )}
            </div>

            {toast && (
                <div className={`toast toast-${toast.type}`}>{toast.msg}</div>
            )}
        </div>
    )
}
