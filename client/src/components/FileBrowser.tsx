import { useState, useEffect } from 'react'
import { api, FileBrowserItem } from '../api'
import { FiFolder, FiChevronRight, FiHardDrive, FiChevronLeft, FiCheck } from 'react-icons/fi'

interface FileBrowserProps {
    onSelect: (path: string) => void
    onClose: () => void
    initialPath?: string
    title?: string
}

export default function FileBrowser({ onSelect, onClose, initialPath, title = 'Select Folder' }: FileBrowserProps) {
    const [currentPath, setCurrentPath] = useState(initialPath || '')
    const [parentPath, setParentPath] = useState<string | undefined>()
    const [items, setItems] = useState<FileBrowserItem[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const loadPath = async (path: string) => {
        setLoading(true)
        setError(null)
        try {
            const res = await api.browseFiles(path)
            setCurrentPath(res.current_path)
            setParentPath(res.parent_path)
            setItems(res.items)
        } catch (e: any) {
            setError(e.message || 'Failed to load directory')
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        loadPath(initialPath || '')
    }, [])

    return (
        <div className="modal-overlay" style={{ zIndex: 1000 }}>
            <div className="modal-content" style={{ maxWidth: '600px', height: '500px', display: 'flex', flexDirection: 'column' }}>
                <div className="modal-header">
                    <h3>{title}</h3>
                    <button className="modal-close" onClick={onClose}>&times;</button>
                </div>
                
                <div style={{ padding: '12px 24px', background: 'var(--bg-primary)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', overflow: 'hidden' }}>
                    <FiHardDrive style={{ flexShrink: 0 }} />
                    <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', direction: 'rtl', textAlign: 'left' }}>
                        {currentPath}
                    </div>
                </div>

                <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
                    {loading ? (
                        <div style={{ padding: '40px', textAlign: 'center' }}><div className="spinner" /></div>
                    ) : error ? (
                        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--error)' }}>{error}</div>
                    ) : (
                        <>
                            {parentPath && (
                                <div 
                                    className="nav-item" 
                                    style={{ padding: '10px 24px', margin: '0' }} 
                                    onClick={() => loadPath(parentPath)}
                                >
                                    <FiChevronLeft className="icon" /> .. (Parent Directory)
                                </div>
                            )}
                            {items.length === 0 ? (
                                <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-tertiary)' }}>No folders found</div>
                            ) : (
                                items.map(item => (
                                    <div 
                                        key={item.path} 
                                        className="nav-item" 
                                        style={{ padding: '10px 24px', margin: '0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
                                        onClick={() => loadPath(item.path)}
                                    >
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                            <FiFolder className="icon" style={{ color: 'var(--accent)' }} />
                                            <span>{item.name}</span>
                                        </div>
                                        <FiChevronRight style={{ opacity: 0.5 }} />
                                    </div>
                                ))
                            )}
                        </>
                    )}
                </div>

                <div className="modal-footer" style={{ padding: '16px 24px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                    <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
                    <button 
                        className="btn btn-primary" 
                        onClick={() => onSelect(currentPath)}
                        disabled={loading}
                    >
                        <FiCheck /> Select Current Folder
                    </button>
                </div>
            </div>
        </div>
    )
}
