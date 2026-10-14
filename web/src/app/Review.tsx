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
  status: string
  kind: 'quote' | 'variation'
  based_on_version: number | null
}

interface VariationDraftLine {
  spoken: string
  kind: 'part' | 'labour' | 'callout' | 'other'
  quantity_milli: number | null
  quantity_vague: boolean
  price_item_id: number | null
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
  const [version, setVersion] = useState<any>(null)
  const [lines, setLines] = useState<QuoteLine[]>([])
  const [loading, setLoading] = useState(true)
  const [approving, setApproving] = useState(false)
  const [ambiguousLine, setAmbiguousLine] = useState<QuoteLine | null>(null)
  const [candidates, setCandidates] = useState<Array<{ price_item_id: number; sku: string; name: string; unit: string; price_cents: number; score: number }>>([])
  const [candidateError, setCandidateError] = useState('')
  const [reviewError, setReviewError] = useState('')
  const [loadingCandidates, setLoadingCandidates] = useState(false)
  const [approverName, setApproverName] = useState('')
  const [priceItems, setPriceItems] = useState<Awaited<ReturnType<typeof api.pricelist.list>>>([])
  const [variationLines, setVariationLines] = useState<VariationDraftLine[]>([])
  const [variationId, setVariationId] = useState('')
  const [variationNumber, setVariationNumber] = useState('')
  const [variationTotalCents, setVariationTotalCents] = useState<number | null>(null)
  const [variationApproved, setVariationApproved] = useState(false)
  const [variationError, setVariationError] = useState('')
  const [variationBusy, setVariationBusy] = useState(false)

  useEffect(() => {
    if (!memoId) return
    let active = true
    let timer: number | undefined

    const pollForQuote = async () => {
      const status = await loadData()
      if (active && status && ['queued', 'uploaded', 'processing'].includes(status)) {
        timer = window.setTimeout(pollForQuote, 1000)
      }
    }
    void pollForQuote()

    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [memoId])

  const loadData = async (): Promise<string | undefined> => {
    setLoading(true)
    try {
      const memoRes = await api.memos.get(memoId!)
      setMemo(memoRes)
      if (memoRes.kind === 'variation' && memoRes.status === 'completed') {
        const extracted = JSON.parse(memoRes.extraction_json || '{}')
        if (Array.isArray(extracted.lines)) {
          setVariationLines(extracted.lines.map((line: {
            spoken: string
            kind: VariationDraftLine['kind']
            quantity?: number | null
            quantity_vague?: boolean
          }) => ({
            spoken: line.spoken,
            kind: line.kind,
            quantity_milli: line.quantity_vague || line.quantity == null
              ? null
              : parseMilliInput(String(line.quantity)),
            quantity_vague: Boolean(line.quantity_vague),
            price_item_id: null,
          })))
          setPriceItems(await api.pricelist.list())
        }
      }
      if (!memoRes.quote_id) {
        setQuote(null)
        setVersion(null)
        setLines([])
        return memoRes.status
      }
      if (memoRes.quote_id) {
        const quoteData = await api.quotes.get(memoRes.quote_id)
        setQuote({
          ...quoteData.quote,
          currency: quoteData.currency,
          vat_rate_bp: quoteData.vat_rate_bp,
        })
        setVersion(quoteData.version)
        setLines(quoteData.lines || [])
      }
      return memoRes.status
    } catch (err) {
      console.error('Failed to load review data:', err)
      setReviewError(err instanceof Error ? err.message : 'Failed to load review data')
      return undefined
    } finally {
      setLoading(false)
    }
  }

  const handleResolve = async (lineId: string, priceItemId: number) => {
    try {
      await api.quotes.updateLine(quote!.id, lineId, { price_item_id: priceItemId })
      await loadData()
      setAmbiguousLine(null)
      setCandidates([])
      setReviewError('')
    } catch (err) {
      console.error('Failed to resolve:', err)
      setCandidateError(err instanceof Error ? err.message : 'Failed to resolve line')
    }
  }

  const handleQuantityChange = async (lineId: string, quantityMilli: number) => {
    try {
      await api.quotes.updateLine(quote!.id, lineId, { quantity_milli: quantityMilli })
      await loadData()
      setReviewError('')
    } catch (err) {
      console.error('Failed to save quantity:', err)
      setReviewError(err instanceof Error ? err.message : 'Failed to save quantity')
    }
  }

  const handleOpenResolve = async (line: QuoteLine) => {
    setAmbiguousLine(line)
    setCandidates([])
    setCandidateError('')
    setLoadingCandidates(true)
    try {
      const result = await api.quotes.getCandidates(quote!.id, line.id)
      setCandidates(result.candidates)
    } catch (err) {
      setCandidateError(err instanceof Error ? err.message : 'Could not load price-list candidates')
    } finally {
      setLoadingCandidates(false)
    }
  }

  const handleApprove = async () => {
    if (!approverName.trim()) return
    setApproving(true)
    try {
      await api.quotes.approve(quote.id, approverName.trim())
      navigate(`/app/quote/${quote.id}`)
    } catch (err) {
      console.error('Failed to approve:', err)
    } finally {
      setApproving(false)
    }
  }

  const updateVariationLine = (index: number, patch: Partial<VariationDraftLine>) => {
    setVariationLines(current => current.map((line, i) => i === index ? { ...line, ...patch } : line))
  }

  const handleCreateVariation = async () => {
    if (!memo?.quote_id || !memo.based_on_version) return
    setVariationBusy(true)
    setVariationError('')
    try {
      const result = await api.variations.create(
        memo.quote_id,
        memo.id,
        memo.based_on_version,
        variationLines.map(line => ({
          spoken: line.spoken,
          kind: line.kind,
          price_item_id: line.price_item_id!,
          quantity_milli: line.quantity_milli!,
        })),
      )
      setVariationId(result.variation_id)
      setVariationNumber(result.number)
      setVariationTotalCents(result.total_cents)
    } catch (err) {
      setVariationError(err instanceof Error ? err.message : 'Could not create variation')
    } finally {
      setVariationBusy(false)
    }
  }

  const handleApproveVariation = async () => {
    if (!variationId || !approverName.trim()) return
    setVariationBusy(true)
    setVariationError('')
    try {
      await api.variations.approve(variationId, approverName.trim())
      setVariationApproved(true)
    } catch (err) {
      setVariationError(err instanceof Error ? err.message : 'Could not approve variation')
    } finally {
      setVariationBusy(false)
    }
  }

  const handleDownloadVariation = async () => {
    try {
      const blob = await api.variations.getPdf(variationId)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${variationNumber || variationId}.pdf`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setVariationError(err instanceof Error ? err.message : 'Could not download variation PDF')
    }
  }

  const allResolved = lines.every(
    line => line.match_outcome === 'confident'
      && line.quantity_milli > 0
      && line.price_item_id !== null,
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-cold-blue border-t-transparent" />
      </div>
    )
  }

  if (!memo || !quote) {
    if (memo && ['queued', 'uploaded', 'processing'].includes(memo.status)) {
      return (
        <div className="card p-8 text-center space-y-3">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-cold-blue border-t-transparent mx-auto" />
          <p className="font-medium text-slate-ink">Processing recording...</p>
          <p className="text-sm text-slate-ink/60">Your memo will appear here when transcription and matching finish.</p>
        </div>
      )
    }
    return (
      <div className="card p-8 text-center">
        <p className="text-hot-red">{reviewError || 'Memo processing failed or quote data is unavailable'}</p>
      </div>
    )
  }

  if (memo.kind === 'variation') {
    if (['queued', 'uploaded', 'processing'].includes(memo.status)) {
      return (
        <div className="card p-8 text-center space-y-3">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-cold-blue border-t-transparent mx-auto" />
          <p className="font-medium text-slate-ink">Processing variation memo...</p>
        </div>
      )
    }
    if (memo.status === 'failed') {
      return <p role="alert" className="text-sm text-hot-red">Variation memo processing failed.</p>
    }
    const readyToCreate = variationLines.length > 0 && variationLines.every(
      line => line.price_item_id !== null && line.quantity_milli !== null && line.quantity_milli > 0,
    )
    return (
      <div className="space-y-6">
        <div className="card p-4 space-y-2">
          <h1 className="font-display text-xl font-semibold">Variation for Quote {quote.number}</h1>
          <p className="text-sm text-slate-ink/60">
            Based on sent version {memo.based_on_version}. Select each price-list item and confirm every quantity; unresolved items are never guessed or priced.
          </p>
          <p className="text-slate-ink bg-teflon p-3 rounded-lg">{memo.transcript}</p>
        </div>
        {variationId ? (
          <div className="card p-5 space-y-4">
            <h2 className="font-display text-lg font-semibold">
              Variation {variationNumber} is pending approval
            </h2>
            {variationTotalCents !== null && (
              <p className="text-lg font-semibold tabular-nums">
                Total: {formatCents(variationTotalCents, quote.currency || 'ZAR')}
              </p>
            )}
            {!variationApproved ? (
              <>
                <label className="block text-sm font-medium" htmlFor="variation-approver">Approver name</label>
                <input
                  id="variation-approver"
                  value={approverName}
                  onChange={event => setApproverName(event.target.value)}
                  className="input-field"
                  maxLength={120}
                  required
                />
                <button
                  onClick={handleApproveVariation}
                  disabled={variationBusy || !approverName.trim()}
                  className="btn-primary w-full"
                >
                  {variationBusy ? 'Approving...' : 'Approve Variation'}
                </button>
              </>
            ) : (
              <>
                <p role="status" className="text-green-700">Approved by {approverName.trim()}.</p>
                <button onClick={handleDownloadVariation} className="btn-primary w-full">
                  Download Variation PDF
                </button>
              </>
            )}
          </div>
        ) : (
          <div className="card divide-y divide-galvanised/50">
            {variationLines.map((line, index) => (
              <div key={`${line.spoken}-${index}`} className="p-4 space-y-3">
                <p className="font-medium">{line.spoken}</p>
                <label className="block text-sm">
                  Price-list item
                  <select
                    value={line.price_item_id ?? ''}
                    onChange={event => updateVariationLine(index, {
                      price_item_id: event.target.value ? Number(event.target.value) : null,
                    })}
                    className="input-field mt-1"
                  >
                    <option value="">Select an item</option>
                    {priceItems.filter(item => (
                      line.kind === 'labour'
                        ? item.category === 'labour' && item.unit === 'hours'
                        : line.kind === 'callout'
                          ? item.category === 'callout'
                          : line.kind === 'part'
                            ? item.category !== 'labour' && item.category !== 'callout' && item.unit !== 'hours'
                            : true
                    )).map(item => (
                      <option key={item.id} value={item.id}>
                        {item.sku} — {item.name} ({formatCents(item.price_cents, item.currency)})
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-sm">
                  Quantity {line.quantity_vague && <span className="text-hot-red">(confirm vague quantity)</span>}
                  <input
                    type="text"
                    inputMode="decimal"
                    value={formatMilliInput(line.quantity_milli)}
                    onChange={event => updateVariationLine(index, {
                      quantity_milli: parseMilliInput(event.target.value),
                    })}
                    className="input-field mt-1"
                    placeholder="Enter quantity"
                  />
                </label>
              </div>
            ))}
            <div className="p-4 space-y-3">
              {variationError && <p role="alert" className="text-sm text-hot-red">{variationError}</p>}
              <button
                onClick={handleCreateVariation}
                disabled={variationBusy || !readyToCreate}
                className="btn-primary w-full"
              >
                {variationBusy ? 'Creating...' : 'Create Variation for Review'}
              </button>
              <button onClick={() => navigate(`/app/quote/${quote.id}`)} className="btn-secondary w-full">
                Back to Quote
              </button>
            </div>
          </div>
        )}
        {variationError && variationId && <p role="alert" className="text-sm text-hot-red">{variationError}</p>}
      </div>
    )
  }

  const currency = quote.currency || 'ZAR'
  const subtotal = version.subtotal_cents
  const vat = version.vat_cents
  const total = version.total_cents
  const vatPercent = (quote.vat_rate_bp / 100).toFixed(2).replace(/\.00$/, '')

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
              onResolve={handleOpenResolve}
              onQuantityChange={handleQuantityChange}
              currency={currency}
            />
          ))}
        </div>
      </div>
      {reviewError && <p role="alert" className="text-sm text-hot-red">{reviewError}</p>}

      <div className="card p-4">
        <div className="space-y-2">
          <div className="flex justify-between">
            <span>Subtotal</span>
            <span className="tabular-nums font-medium">{formatCents(subtotal, currency)}</span>
          </div>
          <div className="flex justify-between">
            <span>VAT ({vatPercent}%)</span>
            <span className="tabular-nums font-medium">{formatCents(vat, currency)}</span>
          </div>
          <div className="border-t border-galvanised pt-2 flex justify-between text-lg font-semibold">
            <span>Total</span>
            <span className="tabular-nums">{formatCents(total, currency)}</span>
          </div>
        </div>
      </div>

      <div className="flex gap-3">
        <label className="sr-only" htmlFor="approver-name">Approver name</label>
        <input
          id="approver-name"
          value={approverName}
          onChange={event => setApproverName(event.target.value)}
          className="input-field"
          placeholder="Your name"
          maxLength={100}
          required
        />
        <button
          onClick={handleApprove}
          disabled={approving || !allResolved || !approverName.trim()}
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
          candidates={candidates}
          currency={currency}
          onResolve={handleResolve}
          onClose={() => setAmbiguousLine(null)}
          loading={loadingCandidates}
          error={candidateError}
        />
      )}
    </div>
  )
}

function formatMilliInput(milli: number | null): string {
  if (milli === null) return ''
  const whole = Math.floor(milli / 1000)
  const fraction = String(milli % 1000).padStart(3, '0').replace(/0+$/, '')
  return fraction ? `${whole}.${fraction}` : String(whole)
}

function parseMilliInput(value: string): number | null {
  if (value === '') return null
  const match = value.match(/^(\d+)(?:\.(\d{1,3}))?$/)
  if (!match) return null
  const quantityMilli = Number(match[1]) * 1000 + Number((match[2] || '').padEnd(3, '0'))
  return Number.isSafeInteger(quantityMilli) ? quantityMilli : null
}
