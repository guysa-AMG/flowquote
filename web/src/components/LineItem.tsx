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

export default function LineItem({ line, onResolve }: Props) {
  const qty = (line.quantity_milli / 1000).toLocaleString(undefined, {
    minimumFractionDigits: line.quantity_milli % 1000 !== 0 ? 3 : 0,
    maximumFractionDigits: 3,
  })

  if (line.match_outcome === 'ambiguous') {
    return (
      <div className="line-item px-4 bg-hivis-yellow/10">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={outcomeClasses.ambiguous}>
              {outcomeIcons.ambiguous} {outcomeLabels.ambiguous}
            </span>
            <span className="font-medium text-slate-ink truncate">{line.spoken}</span>
          </div>
          {line.note && (
            <p className="text-xs text-slate-ink/60 mt-1">{line.note}</p>
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

  if (line.match_outcome === 'no_match') {
    return (
      <div className="line-item px-4 bg-hot-red/5">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={outcomeClasses.no_match}>
              {outcomeIcons.no_match} {outcomeLabels.no_match}
            </span>
            <span className="font-medium text-slate-ink truncate">"{line.spoken}"</span>
          </div>
          <p className="text-xs text-hot-red mt-1">Could not match to price list</p>
        </div>
      </div>
    )
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
          <span className="tabular-nums">{qty} × {formatCents(line.unit_price_cents)}</span>
          <span>=</span>
          <span className="tabular-nums font-medium">{formatCents(line.line_total_cents)}</span>
        </div>
      </div>
      <div className="text-right">
        <span className="tabular-nums font-semibold text-slate-ink">
          {formatCents(line.line_total_cents)}
        </span>
      </div>
    </div>
  )
}
