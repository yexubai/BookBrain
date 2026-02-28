import { useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import LibraryPage from './pages/LibraryPage'
import SearchPage from './pages/SearchPage'
import SettingsPage from './pages/SettingsPage'
import IngestPage from './pages/IngestPage'

export default function App() {
    const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
    const [searchQuery, setSearchQuery] = useState('')

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
                    </Routes>
                </div>
            </div>
        </div>
    )
}
