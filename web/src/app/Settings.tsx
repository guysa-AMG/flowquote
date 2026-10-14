import { useState, useEffect } from 'react'
import { api } from '../lib/api'

interface SystemInfo {
  app_name: string
  version: string
  offline_mode: boolean
  currency: string
  vat_rate_bp: number
  models: { asr: string; llm: string }
}

export default function Settings() {
  const [system, setSystem] = useState<SystemInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [pin, setPin] = useState('')
  const [newPin, setNewPin] = useState('')
  const [confirmPin, setConfirmPin] = useState('')
  const [changingPin, setChangingPin] = useState(false)
  const [pinError, setPinError] = useState('')
  const [pinSuccess, setPinSuccess] = useState('')

  useEffect(() => {
    loadSystem()
  }, [])

  const loadSystem = async () => {
    try {
      const data = await api.system.get()
      setSystem(data)
    } catch (err) {
      console.error('Failed to load system info:', err)
    } finally {
      setLoading(false)
    }
  }

  const handlePinChange = async (e: React.FormEvent) => {
    e.preventDefault()
    setPinError('')
    setPinSuccess('')

    if (!pin || !newPin || !confirmPin) {
      setPinError('All fields are required')
      return
    }

    if (newPin.length !== 4 || !/^\d{4}$/.test(newPin)) {
      setPinError('PIN must be 4 digits')
      return
    }

    if (newPin !== confirmPin) {
      setPinError('New PINs do not match')
      return
    }

    setChangingPin(true)
    try {
      await api.auth.changePin(pin, newPin)
      setPinSuccess('PIN changed successfully')
      setPin('')
      setNewPin('')
      setConfirmPin('')
    } catch (err) {
      setPinError(err instanceof Error ? err.message : 'Failed to change PIN')
    } finally {
      setChangingPin(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-cold-blue border-t-transparent" />
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="font-display text-2xl font-bold text-slate-ink">Settings</h1>

      <div className="card p-4">
        <h2 className="font-display text-lg font-semibold mb-4">System Information</h2>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-slate-ink/60">App</dt>
            <dd className="font-medium">{system?.app_name} v{system?.version}</dd>
          </div>
          <div>
            <dt className="text-slate-ink/60">Offline Mode</dt>
            <dd className="font-medium">{system?.offline_mode ? 'Enabled' : 'Disabled'}</dd>
          </div>
          <div>
            <dt className="text-slate-ink/60">Currency</dt>
            <dd className="font-medium">{system?.currency}</dd>
          </div>
          <div>
            <dt className="text-slate-ink/60">VAT Rate</dt>
            <dd className="font-medium">{(system?.vat_rate_bp ?? 1500) / 100}%</dd>
          </div>
          <div>
            <dt className="text-slate-ink/60">ASR Model</dt>
            <dd className="font-medium">{system?.models.asr}</dd>
          </div>
          <div>
            <dt className="text-slate-ink/60">LLM Model</dt>
            <dd className="font-medium">{system?.models.llm}</dd>
          </div>
        </dl>
      </div>

      <div className="card p-4">
        <h2 className="font-display text-lg font-semibold mb-4">Audio & Storage</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-ink/70 mb-1">Audio Retention</label>
            <p className="text-sm text-slate-ink/60">
              Audio files are deleted immediately after processing by default.
              Change this in the server configuration.
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-ink/70 mb-1">Recording Format</label>
            <p className="text-sm text-slate-ink/60">
              iOS: MP4/AAC · Chrome: WebM/Opus · Converted to 16kHz mono WAV
            </p>
          </div>
        </div>
      </div>

      <div className="card p-4">
        <h2 className="font-display text-lg font-semibold mb-4">Security</h2>
        <form onSubmit={handlePinChange} className="space-y-4">
          <div>
            <label htmlFor="current-pin" className="block text-sm font-medium text-slate-ink/70 mb-1">Current PIN</label>
            <input
              id="current-pin"
              type="password"
              inputMode="numeric"
              pattern="[0-9]*"
              value={pin}
              onChange={e => setPin(e.target.value)}
              className="input-field text-center text-2xl tracking-widest"
              placeholder="••••"
              maxLength={4}
              required
            />
          </div>
          <div>
            <label htmlFor="new-pin" className="block text-sm font-medium text-slate-ink/70 mb-1">New PIN</label>
            <input
              id="new-pin"
              type="password"
              inputMode="numeric"
              pattern="[0-9]*"
              value={newPin}
              onChange={e => setNewPin(e.target.value)}
              className="input-field text-center text-2xl tracking-widest"
              placeholder="••••"
              maxLength={4}
              required
            />
          </div>
          <div>
            <label htmlFor="confirm-pin" className="block text-sm font-medium text-slate-ink/70 mb-1">Confirm New PIN</label>
            <input
              id="confirm-pin"
              type="password"
              inputMode="numeric"
              pattern="[0-9]*"
              value={confirmPin}
              onChange={e => setConfirmPin(e.target.value)}
              className="input-field text-center text-2xl tracking-widest"
              placeholder="••••"
              maxLength={4}
              required
            />
          </div>
          {pinError && <p className="text-sm text-hot-red">{pinError}</p>}
          {pinSuccess && <p className="text-sm text-green-700">{pinSuccess}</p>}
          <button type="submit" disabled={changingPin} className="btn-primary w-full">
            {changingPin ? 'Changing...' : 'Change PIN'}
          </button>
        </form>
      </div>

      <div className="card p-4">
        <h2 className="font-display text-lg font-semibold mb-4">About</h2>
        <p className="text-sm text-slate-ink/60 space-y-2">
          TalkQuote v0.1.0 — Voice-to-quote for plumbers.<br />
          Model extracts. Code prices. Human approves.<br />
          Built for offline-first operation.
        </p>
      </div>
    </div>
  )
}
