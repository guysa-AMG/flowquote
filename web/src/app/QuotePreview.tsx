import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { formatCents } from '../lib/utils'
import { BRAND } from '../brand'

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

export default function QuotePreview() {
  const { quoteId } = useParams<{ quoteId: string }>()
  const navigate = useNavigate()
  const [quote, setQuote] = useState<any>(null)
  const [version, setVersion] = useState<any>(null)
  const [lines, setLines] = useState<QuoteLine[]>([])
  const [currency, setCurrency] = useState('ZAR')
  const [vatRateBp, setVatRateBp] = useState(0)
  const [loading, setLoading] = useState(true)
  const [generatingPdf, setGeneratingPdf] = useState(false)

  useEffect(() => {
    if (!quoteId) return
    loadQuote()
  }, [quoteId])

  const loadQuote = async () => {
    setLoading(true)
    try {
      const data = await api.quotes.get(quoteId!)
      setQuote(data.quote)
      setVersion(data.version)
      setLines(data.lines || [])
      setCurrency(data.currency)
      setVatRateBp(data.vat_rate_bp)
    } catch (err) {
      console.error('Failed to load quote:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleDownloadPdf = async () => {
    setGeneratingPdf(true)
    try {
      const blob = await api.quotes.getPdf(quoteId!)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `quote-${quote?.number || quoteId}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('PDF generation failed:', err)
      alert('Failed to generate PDF')
    } finally {
      setGeneratingPdf(false)
    }
  }

  const handleShare = async () => {
    setGeneratingPdf(true)
    try {
      const blob = await api.quotes.getPdf(quoteId!)
      const file = new File([blob], `quote-${quote?.number || quoteId}.pdf`, { type: 'application/pdf' })

      if (navigator.share && navigator.canShare({ files: [file] })) {
        await navigator.share({
          title: `Quote ${quote?.number}`,
          text: `Quote for ${quote?.customer_name || 'Client'}`,
          files: [file],
        })
      } else {
        // Fallback: download
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = file.name
        a.click()
        URL.revokeObjectURL(url)
      }
    } catch (err) {
      console.error('Share failed:', err)
    } finally {
      setGeneratingPdf(false)
    }
  }

  const handleAddVariation = () => {
    navigate('/app/record', {
      state: { quoteId: quote.id, kind: 'variation', basedOnVersion: version.version },
    })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-cold-blue border-t-transparent" />
      </div>
    )
  }

  if (!quote) {
    return (
      <div className="card p-8 text-center">
        <p className="text-hot-red">Quote not found</p>
        <button onClick={() => navigate('/app/history')} className="btn-primary mt-4">
          Back to History
        </button>
      </div>
    )
  }

  const subtotal = version.subtotal_cents
  const vat = version.vat_cents
  const total = version.total_cents
  const vatPercent = (vatRateBp / 100).toFixed(2).replace(/\.00$/, '')

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="card p-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="font-display text-2xl font-bold text-slate-ink">
              {BRAND.name}
            </h1>
            <p className="text-slate-ink/60">Quote {quote.number} · v{version.version}</p>
          </div>
          <div className="flex gap-2">
            <button onClick={handleDownloadPdf} disabled={generatingPdf} className="btn-secondary">
              📥 Download PDF
            </button>
            <button onClick={handleShare} disabled={generatingPdf} className="btn-primary">
              📤 Share
            </button>
          </div>
        </div>
      </div>

      {/* Client Details */}
      <div className="card p-4 grid gap-3 sm:grid-cols-2">
        <div>
          <p className="text-sm text-slate-ink/60">Client</p>
          <p className="font-medium text-slate-ink">{quote.customer_name || 'Not specified'}</p>
        </div>
        <div>
          <p className="text-sm text-slate-ink/60">Site</p>
          <p className="font-medium text-slate-ink">{quote.site_address || 'Not specified'}</p>
        </div>
        <div>
          <p className="text-sm text-slate-ink/60">Status</p>
          <span className={`px-2 py-1 rounded text-xs font-medium ${
            quote.status === 'sent' ? 'bg-blue-100 text-blue-800' :
            quote.status === 'accepted' ? 'bg-green-100 text-green-800' :
            'bg-galvanised text-slate-ink'
          }`}>
            {quote.status}
          </span>
        </div>
        <div>
          <p className="text-sm text-slate-ink/60">Created</p>
          <p className="font-medium text-slate-ink">
            {new Date(quote.created_at).toLocaleDateString()}
          </p>
        </div>
      </div>

      {/* Line Items */}
      <div className="card overflow-hidden">
        <table className="w-full">
          <thead className="bg-teflon">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-medium text-slate-ink/70">Description</th>
              <th className="px-4 py-3 text-right text-sm font-medium text-slate-ink/70 tabular-nums">Qty</th>
              <th className="px-4 py-3 text-center text-sm font-medium text-slate-ink/70">Unit</th>
              <th className="px-4 py-3 text-right text-sm font-medium text-slate-ink/70 tabular-nums">Unit Price</th>
              <th className="px-4 py-3 text-right text-sm font-medium text-slate-ink/70 tabular-nums">Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-galvanised/50">
            {lines.map(line => (
              <tr key={line.id} className="hover:bg-teflon/50">
                <td className="px-4 py-3">
                  <p className="font-medium text-slate-ink">{line.spoken}</p>
                  {line.note && (
                    <p className="text-xs text-slate-ink/60">{line.note}</p>
                  )}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {formatQuantity(line.quantity_milli)}
                </td>
                <td className="px-4 py-3 text-center text-slate-ink/60">
                  {line.unit}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {formatCents(line.unit_price_cents, currency)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums font-medium">
                  {formatCents(line.line_total_cents, currency)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Totals */}
        <div className="p-4 bg-teflon border-t border-galvanised">
          <div className="flex justify-end space-x-8 max-w-xs ml-auto">
            <div className="space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-slate-ink/70">Subtotal</span>
                <span className="tabular-nums font-medium">{formatCents(subtotal, currency)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-ink/70">VAT ({vatPercent}%)</span>
                <span className="tabular-nums font-medium">{formatCents(vat, currency)}</span>
              </div>
              <div className="border-t border-galvanised pt-1 flex justify-between text-lg font-semibold">
                <span>Total</span>
                <span className="tabular-nums">{formatCents(total, currency)}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3">
        {version.sent_at && (
          <button onClick={handleAddVariation} className="btn-primary flex-1">
            + Add Variation
          </button>
        )}
        <button onClick={() => navigate('/app/history')} className="btn-secondary">
          Back to History
        </button>
      </div>

      {/* Pricing Rule Footer */}
      <div className="card p-4 border-t-2 border-cold-blue">
        <p className="text-xs text-slate-ink/60">
          <strong>Pricing Rule:</strong> line_total = round_half_up(quantity × unit_price);
          subtotal = sum(lines); vat = round_half_up(subtotal × vat_rate / 10000).
          Prices snapshotted at time of quotation.
        </p>
      </div>
    </div>
  )
}

function formatQuantity(milli: number): string {
  const qty = milli / 1000
  if (qty % 1 === 0) return qty.toString()
  if ((milli % 100) === 0) return qty.toFixed(1)
  if ((milli % 10) === 0) return qty.toFixed(2)
  return qty.toFixed(3)
}
