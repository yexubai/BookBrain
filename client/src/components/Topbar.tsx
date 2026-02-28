import { useNavigate } from 'react-router-dom'
import { FiSearch } from 'react-icons/fi'

interface TopbarProps {
    searchQuery: string
    onSearchChange: (q: string) => void
}

export default function Topbar({ searchQuery, onSearchChange }: TopbarProps) {
    const navigate = useNavigate()

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
        </div>
    )
}
