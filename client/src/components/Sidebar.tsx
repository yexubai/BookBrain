import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { api, Category } from '../api'
import {
    FiBook, FiSearch, FiUploadCloud, FiSettings,
    FiChevronRight, FiChevronDown, FiFolder
} from 'react-icons/fi'

interface SidebarProps {
    selectedCategory: string | null
    onSelectCategory: (cat: string | null) => void
}

export default function Sidebar({ selectedCategory, onSelectCategory }: SidebarProps) {
    const [categories, setCategories] = useState<Category[]>([])
    const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set())
    const navigate = useNavigate()
    const location = useLocation()

    useEffect(() => {
        api.getCategories().then(setCategories).catch(() => { })
    }, [])

    const toggleCat = (name: string) => {
        setExpandedCats(prev => {
            const next = new Set(prev)
            if (next.has(name)) next.delete(name)
            else next.add(name)
            return next
        })
    }

    const totalBooks = categories.reduce((sum, c) => sum + c.count, 0)

    return (
        <aside className="sidebar">
            <div className="sidebar-header">
                <a className="sidebar-logo" href="/" onClick={e => { e.preventDefault(); navigate('/') }}>
                    <div className="logo-icon">📚</div>
                    <div>
                        <h1>BookBrain</h1>
                        <span>Ebook Manager</span>
                    </div>
                </a>
            </div>

            <nav className="sidebar-nav">
                <div className="nav-section">
                    <div className="nav-section-title">Menu</div>
                    <button
                        className={`nav-item ${location.pathname === '/' && !selectedCategory ? 'active' : ''}`}
                        onClick={() => { onSelectCategory(null); navigate('/') }}
                    >
                        <FiBook className="icon" />
                        All Books
                        <span className="count">{totalBooks}</span>
                    </button>
                    <button
                        className={`nav-item ${location.pathname === '/search' ? 'active' : ''}`}
                        onClick={() => navigate('/search')}
                    >
                        <FiSearch className="icon" />
                        Semantic Search
                    </button>
                    <button
                        className={`nav-item ${location.pathname === '/ingest' ? 'active' : ''}`}
                        onClick={() => navigate('/ingest')}
                    >
                        <FiUploadCloud className="icon" />
                        Import Books
                    </button>
                    <button
                        className={`nav-item ${location.pathname === '/settings' ? 'active' : ''}`}
                        onClick={() => navigate('/settings')}
                    >
                        <FiSettings className="icon" />
                        Settings
                    </button>
                </div>

                {categories.length > 0 && (
                    <div className="nav-section">
                        <div className="nav-section-title">Categories</div>
                        <div className="category-tree">
                            {categories.map(cat => (
                                <div key={cat.name}>
                                    <div
                                        className={`category-item ${selectedCategory === cat.name ? 'active' : ''}`}
                                        onClick={() => {
                                            onSelectCategory(selectedCategory === cat.name ? null : cat.name)
                                            navigate('/')
                                            if (cat.subcategories.length > 0) toggleCat(cat.name)
                                        }}
                                    >
                                        {cat.subcategories.length > 0 ? (
                                            expandedCats.has(cat.name) ? <FiChevronDown /> : <FiChevronRight />
                                        ) : <FiFolder size={14} />}
                                        <span>{cat.name}</span>
                                        <span className="cat-count">{cat.count}</span>
                                    </div>
                                    {expandedCats.has(cat.name) && cat.subcategories.length > 0 && (
                                        <div className="subcategory-list">
                                            {cat.subcategories.map(sub => (
                                                <div key={sub.name} className="subcategory-item">
                                                    <span>{sub.name}</span>
                                                    <span className="cat-count">{sub.count}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </nav>
        </aside>
    )
}
