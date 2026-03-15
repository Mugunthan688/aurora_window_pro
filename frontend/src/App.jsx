import { Routes, Route, Navigate } from 'react-router-dom'

import Navbar from './components/Navbar'
import Home from './pages/Home'
import LiveMap from './pages/LiveMap'
import Dashboard from './pages/Dashboard'

export default function App() {
  return (
    <div className="app-shell">
      {/* Ambient background layers */}
      <div className="app-bg" aria-hidden="true">
        <div className="app-bg__aurora" />
        <div className="app-bg__stars" />
        <div className="app-bg__vignette" />
      </div>

      <Navbar />

      <main className="app-main">
        <Routes>
          <Route path="/"          element={<Home />} />
          <Route path="/live-map"  element={<LiveMap />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="*"          element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}