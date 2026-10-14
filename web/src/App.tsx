import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { useEffect } from 'react'
import { useAuth } from './hooks/useAuth'
import Layout from './components/Layout'
import Login from './app/Login'
import Record from './app/Record'
import Review from './app/Review'
import QuotePreview from './app/QuotePreview'
import PriceList from './app/PriceList'
import QuoteHistory from './app/QuoteHistory'
import Settings from './app/Settings'

const Showcase = lazy(() => import('./showcase/Showcase'))

function PrivateRoute() {
  const { isAuthenticated, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-teflon">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-cold-blue border-t-transparent" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}

function PublicRoute() {
  const { isAuthenticated, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-teflon">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-cold-blue border-t-transparent" />
      </div>
    )
  }

  if (isAuthenticated) {
    return <Navigate to="/app" replace />
  }

  return <Outlet />
}

export default function App() {
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {})
    }
  }, [])

  return (
    <Routes>
      <Route element={<PublicRoute />}>
        <Route path="/login" element={<Login />} />
      </Route>
      <Route path="/showcase" element={<Suspense fallback={null}><Showcase /></Suspense>} />
      <Route path="/showcase/*" element={<Suspense fallback={null}><Showcase /></Suspense>} />

      <Route element={<PrivateRoute />}>
        <Route path="/app/*" element={<Layout />}>
          <Route index element={<Navigate to="/app/record" replace />} />
          <Route path="record" element={<Record />} />
          <Route path="review/:memoId" element={<Review />} />
          <Route path="quote/:quoteId" element={<QuotePreview />} />
          <Route path="pricelist" element={<PriceList />} />
          <Route path="history" element={<QuoteHistory />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Route>

      <Route path="/" element={<Navigate to="/app/record" replace />} />
      <Route path="*" element={<Navigate to="/app/record" replace />} />
    </Routes>
  )
}
