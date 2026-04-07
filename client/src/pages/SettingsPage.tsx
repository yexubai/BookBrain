import { useState, useEffect } from 'react'
import { api, Settings, getBackendUrl, setBackendUrl, checkBackendHealth, isTauri } from '../api'
import { FiCheck, FiX, FiRefreshCw, FiFolder } from 'react-icons/fi'
import FileBrowser from '../components/FileBrowser'

export default function SettingsPage() {
    const [settings, setSettings] = useState<Settings | null>(null)
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [toast, setToast] = useState<{ type: string; msg: string } | null>(null)

    // Backend connection
    const [backendUrl, setBackendUrlLocal] = useState(getBackendUrl())
    const [connected, setConnected] = useState<boolean | null>(null)
    const [checking, setChecking] = useState(false)

    // Local form state
    const [ebookDirs, setEbookDirs] = useState('')
    const [ocrEnabled, setOcrEnabled] = useState(true)
    const [ocrLang, setOcrLang] = useState('eng+chi_sim')
    const [maxWorkers, setMaxWorkers] = useState(4)
    const [showBrowser, setShowBrowser] = useState(false)

    const checkConnection = async () => {
        setChecking(true)
        const ok = await checkBackendHealth()
        setConnected(ok)
        setChecking(false)
        if (ok) {
            loadSettings()
        }
    }

    const loadSettings = () => {
        api.getSettings().then(s => {
            setSettings(s)
            setEbookDirs(s.ebook_dirs)
            setOcrEnabled(s.ocr_enabled)
            setOcrLang(s.ocr_language)
            setMaxWorkers(s.max_workers)
            setLoading(false)
        }).catch(() => setLoading(false))
    }

    useEffect(() => {
        checkConnection()
    }, [])

    const applyBackendUrl = () => {
        try {
            new URL(backendUrl)
        } catch {
            showToast('error', 'Invalid URL format')
            return
        }
        setBackendUrl(backendUrl)
        showToast('info', 'Backend URL updated')
        checkConnection()
    }

    const saveSettings = async () => {
        setSaving(true)
        try {
            const updated = await api.updateSettings({
                ebook_dirs: ebookDirs,
                ocr_enabled: ocrEnabled,
                ocr_language: ocrLang,
                max_workers: maxWorkers,
            })
            setSettings(updated)
            showToast('success', 'Settings saved!')
        } catch (e: any) {
            showToast('error', e.message || 'Failed to save')
        } finally {
            setSaving(false)
        }
    }

    const showToast = (type: string, msg: string) => {
        setToast({ type, msg })
        setTimeout(() => setToast(null), 4000)
    }

    const handleBrowse = async () => {
        if (isTauri()) {
            try {
                const { open } = await import('@tauri-apps/plugin-dialog')
                const selected = await open({
                    directory: true,
                    multiple: true,
                    defaultPath: ebookDirs.split(',')[0]?.trim() || undefined
                })
                if (selected) {
                    const newPath = Array.isArray(selected) ? selected.join(', ') : (selected as string)
                    setEbookDirs(newPath)
                }
            } catch (e) {
                console.error('Tauri dialog error:', e)
                setShowBrowser(true)
            }
        } else {
            setShowBrowser(true)
        }
    }

    const onBrowserSelect = (path: string) => {
        const newDirs = ebookDirs ? `${ebookDirs}, ${path}` : path
        setEbookDirs(newDirs)
        setShowBrowser(false)
    }

    return (
        <div className="settings-page">
            <div className="page-header">
                <h2>Settings</h2>
            </div>

            {/* Backend Connection */}
            <div className="settings-section">
                <h3>🔗 Backend Connection</h3>
                <div className="setting-row">
                    <div className="setting-label">
                        <div className="label-text">Backend URL</div>
                        <div className="label-desc">
                            {isTauri()
                                ? 'Local backend auto-starts with the app. Change to connect to a remote NAS server instead.'
                                : 'URL of the BookBrain backend server'}
                        </div>
                    </div>
                    <div className="setting-control" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <input
                            type="text"
                            value={backendUrl}
                            onChange={e => setBackendUrlLocal(e.target.value)}
                            placeholder="http://localhost:8000"
                            onKeyDown={e => e.key === 'Enter' && applyBackendUrl()}
                        />
                        <button className="btn-icon" onClick={applyBackendUrl} title="Apply & test">
                            <FiRefreshCw />
                        </button>
                    </div>
                </div>
                <div className="setting-row">
                    <div className="setting-label">
                        <div className="label-text">Status</div>
                    </div>
                    <div className="setting-control" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {checking ? (
                            <span style={{ color: 'var(--text-tertiary)', fontSize: '13px' }}>Checking...</span>
                        ) : connected === true ? (
                            <span style={{ color: 'var(--success)', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <FiCheck /> Connected
                            </span>
                        ) : connected === false ? (
                            <span style={{ color: 'var(--error)', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <FiX /> Not reachable
                            </span>
                        ) : null}
                    </div>
                </div>
            </div>

            {/* Rest of settings only when connected */}
            {connected && !loading && (
                <>
                    <div className="settings-section">
                        <h3>📁 Ebook Directories</h3>
                        <div className="setting-row">
                            <div className="setting-label">
                                <div className="label-text">Scan Directories</div>
                                <div className="label-desc">Comma-separated paths to scan for ebooks</div>
                            </div>
                            <div className="setting-control" style={{ display: 'flex', gap: '8px' }}>
                                <input
                                    type="text"
                                    value={ebookDirs}
                                    onChange={e => setEbookDirs(e.target.value)}
                                    placeholder="e.g., /volume1/ebooks, /data/books"
                                    style={{ flex: 1 }}
                                />
                                <button className="btn btn-secondary" onClick={handleBrowse}>
                                    <FiFolder /> Browse...
                                </button>
                            </div>
                        </div>
                    </div>

                    <div className="settings-section">
                        <h3>🔍 OCR Settings</h3>
                        <div className="setting-row">
                            <div className="setting-label">
                                <div className="label-text">Enable OCR</div>
                                <div className="label-desc">Automatically OCR scanned PDF pages</div>
                            </div>
                            <div className="setting-control">
                                <div
                                    className={`toggle ${ocrEnabled ? 'active' : ''}`}
                                    onClick={() => setOcrEnabled(!ocrEnabled)}
                                >
                                    <div className="toggle-knob" />
                                </div>
                            </div>
                        </div>
                        <div className="setting-row">
                            <div className="setting-label">
                                <div className="label-text">OCR Language</div>
                                <div className="label-desc">Tesseract language codes (e.g., eng, chi_sim)</div>
                            </div>
                            <div className="setting-control">
                                <input
                                    type="text"
                                    value={ocrLang}
                                    onChange={e => setOcrLang(e.target.value)}
                                />
                            </div>
                        </div>
                    </div>

                    <div className="settings-section">
                        <h3>⚡ Performance</h3>
                        <div className="setting-row">
                            <div className="setting-label">
                                <div className="label-text">Max Workers</div>
                                <div className="label-desc">Number of threads for processing</div>
                            </div>
                            <div className="setting-control">
                                <input
                                    type="number"
                                    value={maxWorkers}
                                    onChange={e => setMaxWorkers(Number(e.target.value))}
                                    min={1}
                                    max={16}
                                    style={{ width: '80px' }}
                                />
                            </div>
                        </div>
                    </div>

                    {settings && (
                        <div className="settings-section">
                            <h3>ℹ️ System Info</h3>
                            <div className="setting-row">
                                <div className="setting-label">
                                    <div className="label-text">Embedding Model</div>
                                </div>
                                <div className="setting-control">
                                    <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                                        {settings.embedding_model}
                                    </span>
                                </div>
                            </div>
                            <div className="setting-row">
                                <div className="setting-label">
                                    <div className="label-text">Data Directory</div>
                                </div>
                                <div className="setting-control">
                                    <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                                        {settings.data_dir}
                                    </span>
                                </div>
                            </div>
                        </div>
                    )}

                    <button className="btn btn-primary" onClick={saveSettings} disabled={saving}>
                        {saving ? 'Saving...' : 'Save Settings'}
                    </button>
                </>
            )}

            {connected === false && (
                <div className="empty-state" style={{ padding: '48px' }}>
                    <div className="empty-icon">🔌</div>
                    <h3>Backend not connected</h3>
                    <p>
                        {isTauri()
                            ? 'The local backend may still be starting up. Check that Python and dependencies are installed, or change the URL to connect to a remote server.'
                            : 'Make sure the BookBrain backend is running, or update the URL above to point to your server.'}
                    </p>
                    <button className="btn btn-secondary" onClick={checkConnection}>
                        Retry Connection
                    </button>
                </div>
            )}

            {showBrowser && (
                <FileBrowser 
                    onSelect={onBrowserSelect} 
                    onClose={() => setShowBrowser(false)} 
                    initialPath={ebookDirs.split(',')[0]?.trim()}
                />
            )}

            {toast && (
                <div className={`toast toast-${toast.type}`}>{toast.msg}</div>
            )}
        </div>
    )
}
