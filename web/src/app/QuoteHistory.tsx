import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

interface Quote {
  id: string
  number: string
  customer_name: string | null
  site_address: string | null
  status: string
  created_at: string
}

export default function QuoteHistory() {
  const navigate = useNavigate()
  const [quotes, setQuotes] = useState<Quote[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadQuotes()
  }, [])

  const loadQuotes = async () => {
    try {
      setQuotes([])
    } catch (err) {
      console.error('Failed to load quotes:', err)
    } finally {
      setLoading(false)
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
    <div className="space-y-6">
      <h1 className="font-display text-2xl font-bold text-slate-ink">Quote History</h1>

      {quotes.length === 0 ? (
        <div className="card p-12 text-center">
          <p className="text-slate-ink/60 mb-4">No quotes yet</p>
          <p className="text-sm text-slate-ink/50 mb-6">
            Record a voice memo to create your first quote
          </p>
          <button onClick={() => navigate('/app/record')} className="btn-primary">
            Record Memo
          </button>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full">
            <thead className="bg-teflon">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium text-slate-ink/70">Quote #</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-slate-ink/70">Client</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-slate-ink/70">Site</th>
                <th className="px-4 py-3 text-center text-sm font-medium text-slate-ink/70">Status</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-slate-ink/70 tabular-nums">Total</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-slate-ink/70">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-galvanised/50">
              {quotes.map(quote => (
                <tr key={quote.id} className="hover:bg-teflon/50 cursor-pointer"
                    onClick={() => navigate(`/app/quote/${quote.id}`)}>
                  <td className="px-4 py-3 font-medium text-slate-ink">{quote.number}</td>
                  <td className="px-4 py-3 text-slate-ink">{quote.customer_name || '—'}</td>
                  <td className="px-4 py-3 text-slate-ink/60">{quote.site_address || '—'}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      quote.status === 'sent' ? 'bg-blue-100 text-blue-800' :
                      quote.status === 'accepted' ? 'bg-green-100 text-green-800' :
                      'bg-galvanised text-slate-ink'
                    }`}>
                      {quote.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums font-medium">—</td>
                  <td className="px-4 py-3 text-slate-ink/60">
                    {new Date(quote.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
