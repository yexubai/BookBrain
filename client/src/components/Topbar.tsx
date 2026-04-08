/**
 * Topbar — Global search input and backend connection status indicator.
 *
 * Contains:
 *   - A search input that updates the app-level searchQuery state in real time.
 *     Pressing Enter navigates to the dedicated /search page.
 *   - A connection status dot (green/red) that polls the backend health
 *     endpoint every 15 seconds.  Clicking it navigates to Settings.
 */

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
    const [connected, setConnected] = useState<boolean | null>(null) // null = checking

    // Poll backend health on mount and every 15 seconds
    useEffect(() => {
        checkBackendHealth().then(setConnected).catch(() => setConnected(false))
        const interval = setInterval(() => {
            checkBackendHealth().then(setConnected).catch(() => setConnected(false))
        }, 15000)
        return () => clearInterval(interval)
    }, [])

    /** Navigate to the search page when Enter is pressed with a non-empty query. */
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
