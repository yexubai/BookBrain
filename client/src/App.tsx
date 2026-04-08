/**
 * Root application component.
 *
 * Manages two pieces of top-level state that are shared across pages:
 *   - selectedCategory: the currently active category filter (from Sidebar)
 *   - searchQuery: the current search input text (from Topbar)
 *
 * Layout structure:
 *   ┌──────────┬─────────────────────┐
 *   │ Sidebar  │  Topbar (search)    │
 *   │ (cats)   ├─────────────────────┤
 *   │          │  Page content       │
 *   │          │  (routed)           │
 *   └──────────┴─────────────────────┘
 *
 * Routes:
 *   /         → LibraryPage (book grid/list with filters)
 *   /search   → SearchPage (unified keyword + semantic search)
 *   /ingest   → IngestPage (import management)
 *   /settings → SettingsPage (app configuration)
 *   /reader   → ReaderPage (PDF/EPUB reader with annotations)
 */

import { useState, useEffect } from 'react'
import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import LibraryPage from './pages/LibraryPage'
import SearchPage from './pages/SearchPage'
import SettingsPage from './pages/SettingsPage'
import IngestPage from './pages/IngestPage'
import ReaderPage from './pages/ReaderPage'

export default function App() {
    const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
    const [searchQuery, setSearchQuery] = useState('')

    // Listen for the custom 'clear-category' event dispatched by LibraryPage's "x" button
    useEffect(() => {
        const handler = () => setSelectedCategory(null)
        window.addEventListener('clear-category', handler)
        return () => window.removeEventListener('clear-category', handler)
    }, [])

    return (
        <div className="app">
            <Sidebar
                selectedCategory={selectedCategory}
                onSelectCategory={setSelectedCategory}
            />
            <div className="main-content">
                <Topbar
                    searchQuery={searchQuery}
                    onSearchChange={setSearchQuery}
                />
                <div className="page-content">
                    <Routes>
                        <Route
                            path="/"
                            element={
                                <LibraryPage
                                    selectedCategory={selectedCategory}
                                    searchQuery={searchQuery}
                                />
                            }
                        />
                        <Route
                            path="/search"
                            element={<SearchPage query={searchQuery} />}
                        />
                        <Route path="/ingest" element={<IngestPage />} />
                        <Route path="/settings" element={<SettingsPage />} />
                        <Route path="/reader" element={<ReaderPage />} />
                    </Routes>
                </div>
            </div>
        </div>
    )
}
