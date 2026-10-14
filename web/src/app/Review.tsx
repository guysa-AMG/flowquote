import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { formatCents } from '../lib/utils'
import LineItem from '../components/LineItem'
import AmbiguousModal from '../components/AmbiguousModal'

interface MemoResponse {
  id: string
  transcript: string
  extraction_json: string
  quote_id?: string | null
}

interface QuoteLine {
  id: string
  spoken: string
  price_item_id: number | null
  quantity_milli: number
  unit: string | null
  unit_price_cents: number
  match_outcome: string
  match_score: number
  resolved_by: string
  note: string | null
  line_total_cents: number
  kind: string
  refers_to_previous: string | null
}

export default function Review() {
  const { memoId } = useParams<{ memoId: string }>()
  const navigate = useNavigate()
  const [memo, setMemo] = useState<MemoResponse | null>(null)
  const [quote, setQuote] = useState<any>(null)
  const [lines, setLines] = useState<QuoteLine[]>([])
  const [loading, setLoading] = useState(true)
  const [approving, setApproving] = useState(false)
  const [ambiguousLine, setAmbiguousLine] = useState<QuoteLine | null>(null)

  useEffect(() => {
    if (!memoId) return
    loadData()
  }, [memoId])

  const loadData = async () => {
    setLoading(true)
    try {
      const memoRes = await api.memos.get(memoId!)
      setMemo(memoRes)

      if (memoRes.quote_id) {
        const quoteData = await api.quotes.get(memoRes.quote_id)
        setQuote(quoteData.quote)
        setLines(quoteData.lines || [])
      }
    } catch (err) {
      console.error('Failed to load review data:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleResolve = async (lineId: string, priceItemId: number) => {
    try {
      await api.quotes.updateLine(quote!.id, lineId, { price_item_id: priceItemId })
      setLines(lines.map(l => l.id === lineId ? { ...l, price_item_id: priceItemId, match_outcome: 'confident', resolved_by: 'user' } : l))
      setAmbiguousLine(null)
    } catch (err) {
      console.error('Failed to resolve:', err)
    }
  }

  const handleApprove = async () => {
    setApproving(true)
    try {
      await api.quotes.approve(quote.id, 'Plumber')
      navigate(`/app/quote/${quote.id}`)
    } catch (err) {
      console.error('Failed to approve:', err)
    } finally {
      setApproving(false)
    }
  }

  const allResolved = lines.every(l => l.match_outcome !== 'ambiguous' && l.match_outcome !== 'no_match')

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-cold-blue border-t-transparent" />
      </div>
    )
  }

  if (!memo || !quote) {
    return (
      <div className="card p-8 text-center">
        <p className="text-hot-red">Failed to load quote data</p>
      </div>
    )
  }

  const subtotal = lines.reduce((sum, l) => sum + l.line_total_cents, 0)
  const vat = Math.round(subtotal * 0.15)
  const total = subtotal + vat

  return (
    <div className="space-y-6">
      <div className="card p-4">
        <h3 className="font-medium text-slate-ink/70 mb-2">Transcript</h3>
        <p className="text-slate-ink bg-teflon p-3 rounded-lg">{memo.transcript}</p>
      </div>

      <div className="card">
        <div className="px-4 py-3 border-b border-galvanised flex items-center justify-between">
          <h3 className="font-display text-lg font-semibold">Line Items</h3>
          <span className="text-sm text-slate-ink/60">{lines.length} items</span>
        </div>
        <div className="divide-y divide-galvanised/50">
          {lines.map(line => (
            <LineItem
              key={line.id}
              line={line}
              onResolve={setAmbiguousLine}
            />
          ))}
        </div>
      </div>

      <div className="card p-4">
        <div className="space-y-2">
          <div className="flex justify-between">
            <span>Subtotal</span>
            <span className="tabular-nums font-medium">{formatCents(subtotal)}</span>
          </div>
          <div className="flex justify-between">
            <span>VAT (15%)</span>
            <span className="tabular-nums font-medium">{formatCents(vat)}</span>
          </div>
          <div className="border-t border-galvanised pt-2 flex justify-between text-lg font-semibold">
            <span>Total</span>
            <span className="tabular-nums">{formatCents(total)}</span>
          </div>
        </div>
      </div>

      <div className="flex gap-3">
        <button
          onClick={handleApprove}
          disabled={approving || !allResolved}
          className="btn-primary flex-1 text-lg"
        >
          {approving ? 'Approving...' : allResolved ? 'Approve & Generate PDF' : 'Resolve all flags first'}
        </button>
        <button
          onClick={() => navigate('/app/record')}
          className="btn-secondary"
        >
          Back
        </button>
      </div>

      {ambiguousLine && (
        <AmbiguousModal
          line={ambiguousLine}
          candidates={[]}
          onResolve={handleResolve}
          onClose={() => setAmbiguousLine(null)}
        />
      )}
    </div>
  )
}
