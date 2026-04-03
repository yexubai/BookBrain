import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { FiSearch, FiCircle } from 'react-icons/fi'
import { checkBackendHealth } from '../api'

interface TopbarProps {
    searchQuery: string
    onSearchChange: (q: string) => void
}

export default function Topbar({ searchQuery, onSearchChange }: TopbarProps) {
    const navigate = useNavigate()
    const [connected, setConnected] = useState<boolean | null>(null)

    useEffect(() => {
        checkBackendHealth().then(setConnected).catch(() => setConnected(false))
        const interval = setInterval(() => {
            checkBackendHealth().then(setConnected).catch(() => setConnected(false))
        }, 15000) // Check every 15s
        return () => clearInterval(interval)
    }, [])

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && searchQuery.trim()) {
            navigate('/search')
        }
    }

    return (
        <div className="topbar">
            <div className="search-bar">
                <FiSearch className="search-icon" />
                <input
                    id="global-search"
                    type="text"
                    placeholder="Search books by title, author, or content..."
                    value={searchQuery}
                    onChange={e => onSearchChange(e.target.value)}
                    onKeyDown={handleKeyDown}
                />
            </div>
            <div className="topbar-actions">
                <span
                    title={connected === true ? 'Backend connected' : connected === false ? 'Backend not reachable' : 'Checking...'}
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        fontSize: '12px',
                        color: connected === true ? 'var(--success)' : connected === false ? 'var(--error)' : 'var(--text-tertiary)',
                        cursor: 'pointer',
                    }}
                    onClick={() => navigate('/settings')}
                >
                    <FiCircle
                        size={8}
                        fill={connected === true ? 'var(--success)' : connected === false ? 'var(--error)' : 'var(--text-tertiary)'}
                    />
                    {connected === true ? 'Online' : connected === false ? 'Offline' : '...'}
                </span>
            </div>
        </div>
    )
}
