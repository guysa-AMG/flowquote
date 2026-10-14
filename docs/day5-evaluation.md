# Day 5 evaluation snapshot

`make eval` was run on 2026-10-14 against 21 synthetic typed memos and the 42-item sample price list. This runner uses a local heuristic phrase parser; it does not run ASR or an LLM. Results are a development check, not a model benchmark, pilot result, or production accuracy claim.

| Variant | Item recall | Item precision | Quantity accuracy | Flag rate | Confident-wrong |
|---|---:|---:|---:|---:|---:|
| No aliases | 62.07% (18/29) | 94.74% (18/19) | 61.54% (16/26) | 77.42% (24/31) | 0/7 confident lines |
| Seeded aliases | 93.10% (27/29) | 90.00% (27/30) | 96.15% (25/26) | 38.71% (12/31) | 0/19 confident lines |

Metric denominators are line/item counts, not memo averages. Quantity accuracy excludes truth items whose quantity is intentionally unknown; missing predictions for known quantities count as incorrect. Confident-wrong checks catalog identity against the accepted truth candidates. Exact line predictions and metric definitions are saved in `eval/eval_results.json`.

The run exposed and fixed two safety/data issues: generic seeded `hour(s)` and `labour` aliases could steer an unqualified time phrase toward an after-hours price, and an ambiguous top candidate was being priced in the draft quote. Unqualified labour rates and unspecified-size variants now remain flagged; only confident matches get an automatic price snapshot. Vague quantities remain zero until a human supplies them.

Not measured: audio WER or hotword-on/off (there are no local eval audio files), ASR-size comparison, and LLM model comparison (no comparison corpus/runner was configured). No inference or network access was used for this snapshot.
