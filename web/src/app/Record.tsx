import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

export default function Record() {
  const navigate = useNavigate()
  const [recording, setRecording] = useState(false)
  const [timer, setTimer] = useState(0)
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null)
  const [uploading, setUploading] = useState(false)
  const [customer, setCustomer] = useState('')
  const [site, setSite] = useState('')
  const [offlineCount, setOfflineCount] = useState(0)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerIntervalRef = useRef<number>()
  const streamRef = useRef<MediaStream | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const animationRef = useRef<number>()
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const updateOfflineCount = async () => {
      try {
        const db = await openDB()
        const count = await db.count('memos')
        setOfflineCount(count)
      } catch {
        setOfflineCount(0)
      }
    }
    updateOfflineCount()
    const interval = setInterval(updateOfflineCount, 5000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    if (!recording || !canvasRef.current) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const draw = () => {
      if (!analyserRef.current || !ctx) return

      const bufferLength = analyserRef.current.frequencyBinCount
      const dataArray = new Uint8Array(bufferLength)
      analyserRef.current.getByteFrequencyData(dataArray)

      const width = canvas.width
      const height = canvas.height
      ctx.clearRect(0, 0, width, height)

      ctx.strokeStyle = '#1C57F2'
      ctx.lineWidth = 3
      ctx.lineCap = 'round'
      ctx.beginPath()

      const sliceWidth = width / bufferLength
      let x = 0

      for (let i = 0; i < bufferLength; i++) {
        const v = dataArray[i] / 255.0
        const y = height * (1 - v * 0.5)

        if (i === 0) {
          ctx.moveTo(x, y)
        } else {
          ctx.lineTo(x, y)
        }
        x += sliceWidth
      }

      ctx.stroke()
      animationRef.current = requestAnimationFrame(draw)
    }

    draw()
    return () => cancelAnimationFrame(animationRef.current!)
  }, [recording])

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      })
      streamRef.current = stream

      const audioContext = new AudioContext()
      audioContextRef.current = audioContext
      const source = audioContext.createMediaStreamSource(stream)
      const analyser = audioContext.createAnalyser()
      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0.8
      source.connect(analyser)
      analyserRef.current = analyser

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm',
      })
      mediaRecorderRef.current = mediaRecorder
      chunksRef.current = []

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mediaRecorder.mimeType })
        setAudioBlob(blob)
      }

      mediaRecorder.start(100)
      setRecording(true)
      setTimer(0)

      timerIntervalRef.current = window.setInterval(() => {
        setTimer(t => t + 1)
      }, 1000)

      if ('wakeLock' in navigator) {
        try {
          await (navigator as any).wakeLock.request('screen')
        } catch {}
      }
    } catch (err) {
      console.error('Recording failed:', err)
      alert('Could not access microphone. Please check permissions.')
    }
  }, [])

  const stopRecording = useCallback(async () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    if (audioContextRef.current) {
      await audioContextRef.current.close()
      audioContextRef.current = null
    }
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current)
    }
    setRecording(false)

    if ('wakeLock' in navigator) {
      try {
        await (navigator as any).wakeLock.release()
      } catch {}
    }
  }, [])

  const handleUpload = async () => {
    if (!audioBlob) return

    setUploading(true)
    try {
      const file = new File([audioBlob], `memo-${Date.now()}.webm`, { type: audioBlob.type })
      const result = await api.memos.upload(file, 'quote')
      navigate(`/app/review/${result.memo_id}`)
    } catch (err: any) {
      alert(err.message || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60).toString().padStart(2, '0')
    const s = (seconds % 60).toString().padStart(2, '0')
    return `${m}:${s}`
  }

  return (
    <div className="space-y-6">
      <div className="card p-4 space-y-3">
        <h2 className="font-display text-lg font-semibold text-slate-ink">Job Details</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="block text-sm font-medium text-slate-ink/70 mb-1">Customer</label>
            <input
              type="text"
              value={customer}
              onChange={(e) => setCustomer(e.target.value)}
              className="input-field"
              placeholder="Mr Smith"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-ink/70 mb-1">Site Address</label>
            <input
              type="text"
              value={site}
              onChange={(e) => setSite(e.target.value)}
              className="input-field"
              placeholder="14 Oak Road"
            />
          </div>
        </div>
      </div>

      <div className="card p-6 space-y-6">
        {recording ? (
          <>
            <div className="text-center space-y-4">
              <div className="text-5xl font-display font-bold tabular-nums text-slate-ink">
                {formatTime(timer)}
              </div>

              <div className="relative h-32 mx-auto max-w-xl">
                <canvas
                  ref={canvasRef}
                  className="w-full h-full"
                  width={600}
                  height={128}
                />
              </div>

              <button
                onClick={stopRecording}
                className="btn-destructive w-20 h-20 rounded-full flex items-center justify-center mx-auto text-3xl touch-target"
                aria-label="Stop recording"
              >
                ⏹️
              </button>
            </div>

            <p className="text-center text-sm text-slate-ink/60">
              Recording... Speak clearly into the microphone
            </p>
          </>
        ) : audioBlob ? (
          <>
            <div className="text-center space-y-4">
              <div className="w-20 h-20 rounded-full bg-green-100 flex items-center justify-center mx-auto text-3xl">
                ✅
              </div>
              <h3 className="font-display text-xl font-semibold text-slate-ink">Recording Complete</h3>
              <p className="text-slate-ink/60">Duration: {formatTime(timer)}</p>
            </div>

            <div className="space-y-3">
              <button
                onClick={handleUpload}
                disabled={uploading}
                className="btn-primary w-full text-lg"
              >
                {uploading ? 'Processing...' : 'Upload & Generate Quote'}
              </button>
              <button
                onClick={() => {
                  setAudioBlob(null)
                  setTimer(0)
                }}
                className="btn-secondary w-full"
              >
                Re-record
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="text-center space-y-4">
              <div className="w-24 h-24 rounded-full bg-cold-blue/10 flex items-center justify-center mx-auto text-4xl">
                🎙️
              </div>
              <h3 className="font-display text-xl font-semibold text-slate-ink">Record Voice Memo</h3>
              <p className="text-slate-ink/60">
                Tap the button below and describe the job. We'll transcribe and generate a quote.
              </p>
            </div>

            <button
              onClick={startRecording}
              className="btn-primary w-24 h-24 rounded-full flex items-center justify-center mx-auto text-4xl touch-target"
              aria-label="Start recording"
            >
                🎙️
            </button>

            <p className="text-center text-sm text-slate-ink/50">
              Tap to start recording
            </p>
          </>
        )}
      </div>

      {offlineCount > 0 && (
        <div className="card border-hivis-yellow bg-hivis-yellow/10 p-4">
          <div className="flex items-center gap-2 text-slate-ink">
            <span>☁️</span>
            <span className="font-medium">
              {offlineCount} memo{offlineCount !== 1 ? 's' : ''} waiting to sync
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

// Simple IndexedDB wrapper
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
