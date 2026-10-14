import { Outlet, NavLink } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { BRAND } from '../brand'
import { useState, useEffect } from 'react'

const navItems = [
  { path: '/app/record', label: 'Record', icon: '🎙️' },
  { path: '/app/pricelist', label: 'Price List', icon: '📋' },
  { path: '/app/history', label: 'History', icon: '📜' },
  { path: '/app/settings', label: 'Settings', icon: '⚙️' },
]

export default function Layout() {
  const { logout } = useAuth()

  return (
    <div className="min-h-screen bg-teflon font-body">
      <header className="bg-white border-b border-galvanised sticky top-0 z-40">
        <div className="max-w-4xl mx-auto px-4">
          <div className="flex items-center justify-between h-16">
            <NavLink to="/app/record" className="font-display text-xl font-semibold text-slate-ink">
              {BRAND.name}
            </NavLink>

            <nav className="flex items-center gap-1">
              {navItems.map(item => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-cold-blue text-white'
                        : 'text-slate-ink hover:bg-galvanised'
                    }`
                  }
                >
                  <span>{item.icon}</span>
                  <span>{item.label}</span>
                </NavLink>
              ))}
              <button
                onClick={logout}
                className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-slate-ink hover:bg-galvanised transition-colors"
              >
                <span>🚪</span>
                <span>Logout</span>
              </button>
            </nav>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-6 pb-20">
        <Outlet />
      </main>

      <OfflineIndicator />
    </div>
  )
}

function OfflineIndicator() {
  const [offlineCount, setOfflineCount] = useState(0)

  useEffect(() => {
    const updateCount = async () => {
      try {
        const db = await openDB()
        const count = await db.count('memos')
        setOfflineCount(count)
      } catch {
        setOfflineCount(0)
      }
    }

    updateCount()
    window.addEventListener('online', updateCount)
    window.addEventListener('focus', updateCount)
    const interval = setInterval(updateCount, 5000)
    return () => {
      window.removeEventListener('online', updateCount)
      window.removeEventListener('focus', updateCount)
      clearInterval(interval)
    }
  }, [])

  if (offlineCount === 0) return null

  return (
    <div className="fixed bottom-4 left-4 right-4 md:left-auto md:right-4 md:w-72 z-50 animate-slide-up">
      <div className="bg-hivis-yellow border border-galvanised rounded-lg p-3 text-slate-ink text-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span>☁️</span>
            <span className="font-medium">
              {offlineCount} memo{offlineCount !== 1 ? 's' : ''} waiting to sync
            </span>
          </div>
          {navigator.onLine && (
            <span className="text-xs text-slate-ink/70">Syncing...</span>
          )}
        </div>
      </div>
    </div>
  )
}

// Simple IndexedDB wrapper for offline queue
async function openDB(): Promise<any> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('TalkQuote', 1)
    request.onerror = () => reject(request.error)
    request.onsuccess = () => resolve(request.result)
    request.onupgradeneeded = (e) => {
      const db = (e.target as IDBOpenDBRequest).result
      if (!db.objectStoreNames.contains('memos')) {
        db.createObjectStore('memos', { keyPath: 'id' })
      }
    }
  })
}
