import { useEffect, useRef } from 'react'
import { formatCents } from '../lib/utils'
import { createPortal } from 'react-dom'

interface Props {
  line: {
    id: string
    spoken: string
    note: string | null
  }
  candidates: Array<{
    id: number
    name: string
    unit: string
    price_cents: number
  }>
  onResolve: (lineId: string, priceItemId: number) => void
  onClose: () => void
}

export default function AmbiguousModal({ line, candidates, onResolve, onClose }: Props) {
  const overlayRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = ''
    }
  }, [onClose])

  useEffect(() => {
    overlayRef.current?.focus()
  }, [])

  const content = (
    <div
      ref={overlayRef}
      tabIndex={-1}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 animate-fade-in"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div
        className="card w-full max-w-md animate-slide-up"
        onClick={e => e.stopPropagation()}
      >
        <div className="p-4 border-b border-galvanised">
          <h2 id="modal-title" className="font-display text-lg font-semibold text-slate-ink">
            Resolve: "{line.spoken}"
          </h2>
          {line.note && (
            <p className="text-sm text-hivis-yellow/80 mt-1">{line.note}</p>
          )}
        </div>

        <div className="p-4 space-y-2 max-h-[60vh] overflow-y-auto">
          {candidates.map(candidate => (
            <button
              key={candidate.id}
              onClick={() => onResolve(line.id, candidate.id)}
              className="w-full text-left p-3 rounded-lg border border-galvanised hover:bg-teflon transition-colors"
            >
              <div className="font-medium text-slate-ink">{candidate.name}</div>
              <div className="flex items-center gap-3 text-sm text-slate-ink/60 mt-1">
                <span className="tabular-nums">{formatCents(candidate.price_cents)}/{candidate.unit}</span>
              </div>
            </button>
          ))}
        </div>

        <div className="px-4 pb-4 pt-2 border-t border-galvanised">
          <button
            onClick={onClose}
            className="btn-secondary w-full"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )

  return createPortal(content, document.body)
}
