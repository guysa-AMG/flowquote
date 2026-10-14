import { useState } from 'react'
import { formatCents } from '../lib/utils'

interface Props {
  line: {
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
  onResolve: (line: any) => void
  onQuantityChange: (lineId: string, quantityMilli: number) => void
  currency: string
}

const outcomeIcons = {
  confident: '✅',
  ambiguous: '⚠️',
  no_match: '❌',
}

const outcomeLabels = {
  confident: 'Matched',
  ambiguous: 'Pick one',
  no_match: 'No match',
}

const outcomeClasses = {
  confident: 'badge-confident',
  ambiguous: 'badge-ambiguous',
  no_match: 'badge-no-match',
}

export default function LineItem({ line, onResolve, onQuantityChange, currency }: Props) {
  const [quantityInput, setQuantityInput] = useState('')
  const qty = (line.quantity_milli / 1000).toLocaleString(undefined, {
    minimumFractionDigits: line.quantity_milli % 1000 !== 0 ? 3 : 0,
    maximumFractionDigits: 3,
  })
  const parsedQuantity = parseQuantityMilli(quantityInput)

  if (line.match_outcome === 'ambiguous' || line.match_outcome === 'no_match') {
    const noMatch = line.match_outcome === 'no_match'
    return (
      <div className={`line-item px-4 ${noMatch ? 'bg-hot-red/5' : 'bg-hivis-yellow/10'}`}>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={noMatch ? outcomeClasses.no_match : outcomeClasses.ambiguous}>
              {noMatch ? outcomeIcons.no_match : outcomeIcons.ambiguous} {noMatch ? outcomeLabels.no_match : outcomeLabels.ambiguous}
            </span>
            <span className="font-medium text-slate-ink truncate">{line.spoken}</span>
          </div>
          {(line.note || noMatch) && (
            <p className="text-xs text-slate-ink/60 mt-1">{line.note || 'Could not match to price list'}</p>
          )}
          {line.quantity_milli === 0 && (
            <div className="mt-2 flex items-center gap-2">
              <label className="text-sm" htmlFor={`quantity-${line.id}`}>Quantity</label>
              <input
                id={`quantity-${line.id}`}
                type="text"
                inputMode="decimal"
                value={quantityInput}
                onChange={event => setQuantityInput(event.target.value)}
                className="input-field w-28"
                placeholder="e.g. 2.5"
                aria-label={`Quantity for ${line.spoken}`}
              />
              <button
                onClick={() => parsedQuantity !== null && onQuantityChange(line.id, parsedQuantity)}
                disabled={parsedQuantity === null}
                className="btn-secondary text-sm"
              >
                Save quantity
              </button>
            </div>
          )}
        </div>
        <button
          onClick={() => onResolve(line)}
          className="btn-secondary text-sm whitespace-nowrap"
        >
          Resolve
        </button>
      </div>
    )
  }

  function parseQuantityMilli(value: string): number | null {
    if (!/^\d+(?:\.\d{1,3})?$/.test(value)) return null
    const [whole, fraction = ''] = value.split('.')
    const quantityMilli = Number(whole) * 1000 + Number(fraction.padEnd(3, '0'))
    return Number.isSafeInteger(quantityMilli) && quantityMilli > 0
      ? quantityMilli
      : null
  }

  return (
    <div className="line-item px-4">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={outcomeClasses.confident}>
            {outcomeIcons.confident} {outcomeLabels.confident}
          </span>
          <span className="font-medium text-slate-ink truncate">{line.spoken}</span>
        </div>
        <div className="flex items-center gap-4 text-sm text-slate-ink/60 mt-1">
          <span className="tabular-nums">{qty} × {formatCents(line.unit_price_cents, currency)}</span>
          <span>=</span>
          <span className="tabular-nums font-medium">{formatCents(line.line_total_cents, currency)}</span>
        </div>
      </div>
      <div className="text-right">
        <span className="tabular-nums font-semibold text-slate-ink">
          {formatCents(line.line_total_cents, currency)}
        </span>
      </div>
    </div>
  )
}
