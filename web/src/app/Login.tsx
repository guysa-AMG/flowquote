import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { BRAND } from '../brand'

export default function Login() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(pin)
      navigate('/app/record')
    } catch (err: any) {
      setError(err.message || 'Invalid PIN')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-teflon px-4">
      <div className="w-full max-w-md card p-8">
        <div className="text-center mb-8">
          <h1 className="font-display text-3xl font-bold text-slate-ink mb-2">{BRAND.name}</h1>
          <p className="text-slate-ink/60">{BRAND.tagline}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label htmlFor="pin" className="block text-sm font-medium text-slate-ink mb-2">
              PIN
            </label>
            <input
              id="pin"
              type="password"
              inputMode="numeric"
              pattern="[0-9]*"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              className="input-field text-center text-2xl tracking-widest"
              placeholder="••••"
              maxLength={4}
              autoComplete="one-time-code"
              required
              disabled={loading}
            />
          </div>

          {error && (
            <div className="bg-hot-red/10 border border-hot-red/20 text-hot-red rounded-lg p-3 text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || pin.length !== 4}
            className="btn-primary w-full text-lg"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-slate-ink/50">
          Default PIN: <code className="bg-galvanised px-1.5 py-0.5 rounded">1234</code>
        </p>
      </div>
    </div>
  )
}
