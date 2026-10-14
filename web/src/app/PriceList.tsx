import { useState, useEffect, FormEvent } from 'react'
import { api } from '../lib/api'
import { formatCents } from '../lib/utils'

interface PriceItem {
  id: number
  sku: string
  name: string
  unit: string
  price_cents: number
  category: string
  attrs: Record<string, string>
  active: number
}

export default function PriceList() {
  const [items, setItems] = useState<PriceItem[]>([])
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState(false)
  const [showImport, setShowImport] = useState(false)

  useEffect(() => {
    loadItems()
  }, [])

  const loadItems = async () => {
    try {
      const data = await api.pricelist.list()
      setItems(data)
    } catch (err) {
      console.error('Failed to load price list:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleImport = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)
    const file = formData.get('file') as File
    if (!file) return

    setImporting(true)
    try {
      await api.pricelist.import(file)
      setShowImport(false)
      await loadItems()
      alert('Price list imported successfully')
    } catch (err: any) {
      alert(err.message || 'Import failed')
    } finally {
      setImporting(false)
      e.currentTarget.reset()
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
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold text-slate-ink">Price List</h1>
        <div className="flex gap-2">
          <button onClick={() => setShowImport(true)} className="btn-secondary">
            📥 Import CSV
          </button>
        </div>
      </div>

      {/* Import Modal */}
      {showImport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="card w-full max-w-md animate-slide-up">
            <div className="p-4 border-b border-galvanised flex items-center justify-between">
              <h2 className="font-display text-lg font-semibold">Import Price List</h2>
              <button onClick={() => setShowImport(false)} className="text-slate-ink/50 hover:text-slate-ink">✕</button>
            </div>
            <form onSubmit={handleImport} className="p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">CSV File</label>
                <input
                  type="file"
                  name="file"
                  accept=".csv"
                  required
                  className="input-field"
                />
              </div>
              <p className="text-xs text-slate-ink/60">
                Required columns: sku, name, unit, price_cents, category, attrs_json (optional)
              </p>
              <div className="flex gap-2 pt-2">
                <button type="button" onClick={() => setShowImport(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" disabled={importing} className="btn-primary flex-1">
                  {importing ? 'Importing...' : 'Import'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Price List Table */}
      <div className="card overflow-hidden">
        <table className="w-full">
          <thead className="bg-teflon">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-medium text-slate-ink/70">SKU</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-slate-ink/70">Name</th>
              <th className="px-4 py-3 text-center text-sm font-medium text-slate-ink/70">Unit</th>
              <th className="px-4 py-3 text-right text-sm font-medium text-slate-ink/70 tabular-nums">Price</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-slate-ink/70">Category</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-slate-ink/70">Attributes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-galvanised/50">
            {items.map(item => (
              <tr key={item.id} className="hover:bg-teflon/50">
                <td className="px-4 py-3 font-mono text-sm text-slate-ink">{item.sku}</td>
                <td className="px-4 py-3 font-medium text-slate-ink">{item.name}</td>
                <td className="px-4 py-3 text-center text-slate-ink/60">{item.unit}</td>
                <td className="px-4 py-3 text-right tabular-nums font-medium">{formatCents(item.price_cents)}</td>
                <td className="px-4 py-3 text-slate-ink/60 capitalize">{item.category}</td>
                <td className="px-4 py-3 text-xs text-slate-ink/50 font-mono">
                  {Object.entries(item.attrs).map(([k, v]) => `${k}:${v}`).join(', ') || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {items.length === 0 && (
        <div className="card p-8 text-center text-slate-ink/60">
          No price items found. Import a CSV to get started.
        </div>
      )}
    </div>
  )
}
