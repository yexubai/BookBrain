import { useState, useEffect } from 'react'
import { api, Settings } from '../api'

export default function SettingsPage() {
    const [settings, setSettings] = useState<Settings | null>(null)
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [toast, setToast] = useState<{ type: string; msg: string } | null>(null)

    // Local form state
    const [ebookDirs, setEbookDirs] = useState('')
    const [ocrEnabled, setOcrEnabled] = useState(true)
    const [ocrLang, setOcrLang] = useState('eng+chi_sim')
    const [maxWorkers, setMaxWorkers] = useState(4)

    useEffect(() => {
        api.getSettings().then(s => {
            setSettings(s)
            setEbookDirs(s.ebook_dirs)
            setOcrEnabled(s.ocr_enabled)
            setOcrLang(s.ocr_language)
            setMaxWorkers(s.max_workers)
            setLoading(false)
        }).catch(() => setLoading(false))
    }, [])

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
            setToast({ type: 'success', msg: 'Settings saved!' })
            setTimeout(() => setToast(null), 3000)
        } catch (e: any) {
            setToast({ type: 'error', msg: e.message || 'Failed to save' })
            setTimeout(() => setToast(null), 5000)
        } finally {
            setSaving(false)
        }
    }

    if (loading) {
        return <div className="loading"><div className="spinner" /></div>
    }

    return (
        <div className="settings-page">
            <div className="page-header">
                <h2>Settings</h2>
            </div>

            <div className="settings-section">
                <h3>📁 Ebook Directories</h3>
                <div className="setting-row">
                    <div className="setting-label">
                        <div className="label-text">Scan Directories</div>
                        <div className="label-desc">Comma-separated paths to scan for ebooks</div>
                    </div>
                    <div className="setting-control">
                        <input
                            type="text"
                            value={ebookDirs}
                            onChange={e => setEbookDirs(e.target.value)}
                            placeholder="e.g., /volume1/ebooks, /data/books"
                        />
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

            {toast && (
                <div className={`toast toast-${toast.type}`}>{toast.msg}</div>
            )}
        </div>
    )
}
