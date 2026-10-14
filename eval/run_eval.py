#!/usr/bin/env python3
"""Evaluation harness runner (PLAN.md §12).

Computes metrics on typed phrases (no audio needed for CI).
Full audio eval runs locally via `make eval` with real audio files.

Metrics:
- Item recall and precision
- Quantity accuracy
- Confident-wrong rate (safety metric, target ~0)
- Flag rate
- Price correctness on matched lines (100% by construction)
- WER (with and without hotwords) — requires audio
"""
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from decimal import Decimal

from app.db import (
    fetch_price_items,
    get_db,
    init_db,
    seed_default_aliases,
    seed_default_price_items,
)
from app.extract import SpokenLine
from app.match import PriceItemCandidate, match_line
from app.pricing import calculate_line_total_cents, qty_to_milli


@dataclass
class EvalResult:
    memo_id: str
    transcript: str
    expected_items: list[dict]
    predicted_lines: list[dict]
    item_recall: float
    item_precision: float
    quantity_accuracy: float
    confident_wrong: bool
    flag_rate: float
    price_correct: bool
    true_positive_count: int
    expected_item_count: int
    predicted_item_count: int
    quantity_correct_count: int
    expected_quantity_count: int
    confident_wrong_count: int
    confident_line_count: int
    flagged_line_count: int
    line_count: int


def load_price_items_and_aliases(
    db_path: str | Path | None = None,
) -> tuple[list[PriceItemCandidate], dict[str, str]]:
    """Load price items and alias map (phrase -> standard text) from DB."""
    with get_db(db_path) as conn:
        seed_default_price_items(conn, business_id="biz_default")
        seed_default_aliases(conn, business_id="biz_default")
        raw_items = fetch_price_items(conn, business_id="biz_default")

        # Load aliases - map from phrase to the price item's name (standard text)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.phrase, p.name as standard_name
            FROM alias a
            JOIN price_item p ON p.id = a.price_item_id
            WHERE a.business_id = ?
        """, ("biz_default",))
        alias_rows = cursor.fetchall()
        alias_map = {row["phrase"]: row["standard_name"] for row in alias_rows}

    items = [
        PriceItemCandidate(
            id=item["id"],
            sku=item["sku"],
            name=item["name"],
            unit=item["unit"],
            price_cents=item["price_cents"],
            category=item["category"],
            attrs=item.get("attrs", {}) or {},
        )
        for item in raw_items
    ]

    return items, alias_map


def extract_lines_local(transcript: str) -> list[SpokenLine]:
    """Local extraction fallback (no LLM) for CI evaluation.
    Splits transcript and extracts quantity/kind heuristically."""
    import re

    number_words = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "a": 1, "an": 1, "couple": 2, "few": 3, "some": 1,
    }

    def split_phrases(text: str) -> list[str]:
        cleaned = text.strip()
        if not cleaned:
            return []
        parts = re.split(r"[,;]|\s+and\s+|\s+then\s+", cleaned, flags=re.IGNORECASE)
        return [p.strip() for p in parts if p.strip()]

    def extract_qty(phrase: str) -> tuple[Decimal | None, bool]:
        working = re.sub(r"\b\d+(?:\.\d+)?\s*mm²?\b", "", phrase, flags=re.IGNORECASE)
        match = re.search(r"\b(\d+(?:\.\d+)?)\b", working)
        if match:
            return Decimal(match.group(1)), False
        for word, value in sorted(number_words.items(), key=lambda kv: len(kv[0]), reverse=True):
            if re.search(rf"\b{word}\b", working, flags=re.IGNORECASE):
                if word in ("couple", "few", "some"):
                    return Decimal(str(value)), True
                return Decimal(str(value)), False
        return None, False

    def detect_kind(phrase: str) -> str:
        low = phrase.lower()
        if any(w in low for w in ["labour", "labor", "hour", "hours"]):
            return "labour"
        if any(w in low for w in ["callout", "call-out", "trip"]):
            return "callout"
        return "part"

    def detect_unit(phrase: str) -> str | None:
        low = phrase.lower()
        if "hour" in low:
            return "hours"
        if "metre" in low or "meter" in low or re.search(r"\bmm\b", low):
            return "m"
        return "each"

    lines = []
    for phrase in split_phrases(transcript):
        qty, vague = extract_qty(phrase)
        lines.append(SpokenLine(
            spoken=phrase,
            kind=detect_kind(phrase),
            quantity=qty,
            quantity_vague=vague,
            unit=detect_unit(phrase),
            refers_to_previous=None,
        ))
    return lines


def match_lines(extracted: list[SpokenLine], price_items: list[PriceItemCandidate], alias_map: dict[str, str]) -> list[dict]:
    """Match each extracted line to price items using alias map."""
    results = []
    for line in extracted:
        result = match_line(line.spoken, price_items, alias_map=alias_map)
        qty_milli = (
            0
            if line.quantity_vague
            else qty_to_milli(line.quantity) if line.quantity is not None else 1000
        )
        has_priceable_match = result.best_match is not None and not line.quantity_vague
        results.append({
            "spoken": line.spoken,
            "kind": line.kind,
            "quantity_milli": qty_milli,
            "unit": line.unit,
            "quantity_vague": line.quantity_vague,
            "match_outcome": (
                "ambiguous" if line.quantity_vague else result.outcome.value
            ),
            "match_score": result.best_score,
            "price_item_id": result.best_match.id if has_priceable_match else None,
            # Keep the top candidate for evaluation/debugging, but do not imply
            # it was selected or priced when quantity certainty is missing.
            "matched_sku": result.best_match.sku if result.best_match else None,
            "matched_name": result.best_match.name if result.best_match else None,
            "unit_price_cents": (
                result.best_match.price_cents if has_priceable_match else 0
            ),
            "line_total_cents": (
                calculate_line_total_cents(qty_milli, result.best_match.price_cents)
                if has_priceable_match
                else 0
            ),
            "flag_reason": result.flag_reason,
        })
    return results


def _acceptable_skus(expected_item: dict) -> set[str]:
    """Return the truth SKU or the explicitly allowed candidates for an item."""
    if "sku" in expected_item:
        return {expected_item["sku"]}
    return set(expected_item.get("acceptable_skus", []))


def _pair_expected_and_predicted(
    expected_items: list[dict],
    predicted_lines: list[dict],
) -> list[tuple[dict, dict]]:
    """Greedily match each expected item to one compatible prediction."""
    remaining = [
        line for line in predicted_lines
        if line.get("matched_sku") is not None
    ]
    expected_order = sorted(
        expected_items,
        key=lambda item: (len(_acceptable_skus(item)), item.get("quantity_milli") is None),
    )
    pairs = []
    for expected in expected_order:
        candidates = [
            line for line in remaining
            if line["matched_sku"] in _acceptable_skus(expected)
        ]
        if not candidates:
            continue
        expected_quantity = expected.get("quantity_milli")
        candidates.sort(
            key=lambda line: (
                expected_quantity is not None
                and line["quantity_milli"] != expected_quantity,
                line["match_outcome"] != "confident",
            )
        )
        selected = candidates[0]
        remaining.remove(selected)
        pairs.append((expected, selected))
    return pairs


def evaluate_memo(
    memo_id: str,
    transcript: str,
    expected_items: list[dict],
    price_items: list[PriceItemCandidate],
    alias_map: dict[str, str],
) -> EvalResult:
    """Evaluate a single memo against ground truth."""
    # Extract lines (local fallback for CI)
    extracted = extract_lines_local(transcript)

    # Match against price list with aliases
    predicted = match_lines(extracted, price_items, alias_map)

    pairs = _pair_expected_and_predicted(expected_items, predicted)
    expected_count = len(expected_items)
    predicted_count = sum(line["matched_sku"] is not None for line in predicted)
    true_positive_count = len(pairs)
    item_recall = true_positive_count / expected_count if expected_count else 1.0
    item_precision = true_positive_count / predicted_count if predicted_count else (
        1.0 if expected_count == 0 else 0.0
    )

    quantity_expected_count = sum(
        item.get("quantity_milli") is not None for item in expected_items
    )
    quantity_correct_count = sum(
        expected.get("quantity_milli") is not None
        and line["quantity_milli"] == expected["quantity_milli"]
        for expected, line in pairs
    )
    quantity_accuracy = (
        quantity_correct_count / quantity_expected_count
        if quantity_expected_count
        else 1.0
    )

    confident_lines = [
        line for line in predicted if line["match_outcome"] == "confident"
    ]
    expected_skus = set().union(
        *(_acceptable_skus(item) for item in expected_items)
    ) if expected_items else set()
    confident_wrong_count = sum(
        line["matched_sku"] not in expected_skus for line in confident_lines
    )
    confident_wrong = confident_wrong_count > 0

    flagged_line_count = sum(
        line["match_outcome"] in ("ambiguous", "no_match")
        for line in predicted
    )
    flag_rate = flagged_line_count / len(predicted) if predicted else 0.0

    catalog_prices = {item.sku: item.price_cents for item in price_items}
    priceable_lines = [
        line for line in predicted if line["match_outcome"] == "confident"
    ]
    price_correct = all(
        line["matched_sku"] in catalog_prices
        and line["unit_price_cents"] == catalog_prices[line["matched_sku"]]
        and line["line_total_cents"]
        == calculate_line_total_cents(
            line["quantity_milli"], catalog_prices[line["matched_sku"]]
        )
        for line in priceable_lines
    )

    return EvalResult(
        memo_id=memo_id,
        transcript=transcript,
        expected_items=expected_items,
        predicted_lines=predicted,
        item_recall=item_recall,
        item_precision=item_precision,
        quantity_accuracy=quantity_accuracy,
        confident_wrong=confident_wrong,
        flag_rate=flag_rate,
        price_correct=price_correct,
        true_positive_count=true_positive_count,
        expected_item_count=expected_count,
        predicted_item_count=predicted_count,
        quantity_correct_count=quantity_correct_count,
        expected_quantity_count=quantity_expected_count,
        confident_wrong_count=confident_wrong_count,
        confident_line_count=len(confident_lines),
        flagged_line_count=flagged_line_count,
        line_count=len(predicted),
    )


def summarize_results(results: list[EvalResult]) -> dict:
    """Aggregate micro metrics so missing/duplicate lines cannot disappear."""
    expected_items = sum(result.expected_item_count for result in results)
    predicted_items = sum(result.predicted_item_count for result in results)
    true_positives = sum(result.true_positive_count for result in results)
    expected_quantities = sum(result.expected_quantity_count for result in results)
    quantity_correct = sum(result.quantity_correct_count for result in results)
    line_count = sum(result.line_count for result in results)
    confident_lines = sum(result.confident_line_count for result in results)
    confident_wrong = sum(result.confident_wrong_count for result in results)
    flagged_lines = sum(result.flagged_line_count for result in results)

    return {
        "total_memos": len(results),
        "line_count": line_count,
        "expected_item_count": expected_items,
        "predicted_item_count": predicted_items,
        "item_recall": true_positives / expected_items if expected_items else 1.0,
        "item_precision": true_positives / predicted_items if predicted_items else (
            1.0 if expected_items == 0 else 0.0
        ),
        "quantity_expected_count": expected_quantities,
        "quantity_correct_count": quantity_correct,
        "quantity_accuracy": (
            quantity_correct / expected_quantities if expected_quantities else 1.0
        ),
        "flagged_line_count": flagged_lines,
        "flag_rate": flagged_lines / line_count if line_count else 0.0,
        "confident_line_count": confident_lines,
        "confident_wrong_count": confident_wrong,
        "confident_wrong_rate": (
            confident_wrong / confident_lines if confident_lines else 0.0
        ),
        "price_correctness": all(result.price_correct for result in results),
    }


def run_variant(
    memos: list[dict],
    price_items: list[PriceItemCandidate],
    alias_map: dict[str, str],
) -> tuple[dict, list[EvalResult]]:
    results = [
        evaluate_memo(
            memo["memo_id"],
            memo["transcript"],
            memo["expected_items"],
            price_items,
            alias_map,
        )
        for memo in memos
    ]
    return summarize_results(results), results


def run_evaluation():
    truth_path = Path(__file__).parent / "truth.jsonl"
    if not truth_path.exists():
        print("No truth.jsonl found.")
        return

    # Seed an isolated scratch DB so eval does not mutate app data or reuse
    # stale alias rows from an earlier run.
    with TemporaryDirectory(prefix="talkquote-eval-") as scratch_dir:
        eval_db = Path(scratch_dir) / "eval.sqlite"
        init_db(eval_db)
        price_items, alias_map = load_price_items_and_aliases(eval_db)
    print(f"Loaded {len(price_items)} price items and {len(alias_map)} aliases")

    # Load truth data
    memos = []
    with open(truth_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                memos.append(json.loads(line))

    print(f"Evaluating {len(memos)} synthetic typed memos with heuristic extraction.\n")

    without_aliases, _ = run_variant(memos, price_items, {})
    with_aliases, results = run_variant(memos, price_items, alias_map)
    variants = {
        "no_aliases": without_aliases,
        "seeded_aliases": with_aliases,
    }
    print("BASELINE COMPARISON (typed synthetic phrases; heuristic extraction)")
    for name, metrics in variants.items():
        print(
            f"{name}: recall={metrics['item_recall']:.2%}, "
            f"precision={metrics['item_precision']:.2%}, "
            f"quantity={metrics['quantity_accuracy']:.2%}, "
            f"flag={metrics['flag_rate']:.2%}, "
            f"confident-wrong={metrics['confident_wrong_count']}/"
            f"{metrics['confident_line_count']}"
        )

    print("\nPER-MEMO BREAKDOWN (seeded aliases):")
    for result in results:
        print(
            f"  {result.memo_id}: R={result.item_recall:.0%} "
            f"P={result.item_precision:.0%} Qty={result.quantity_accuracy:.0%} "
            f"Flags={result.flag_rate:.0%} "
            f"CW={result.confident_wrong_count}/{result.confident_line_count}"
        )

    audio_dir = Path(__file__).parent / "audio"
    audio_count = sum(
        path.is_file()
        for pattern in ("*.wav", "*.mp3", "*.m4a", "*.mp4", "*.webm", "*.ogg")
        for path in audio_dir.glob(pattern)
    ) if audio_dir.is_dir() else 0
    output = {
        "dataset": {
            "kind": "synthetic typed transcripts",
            "memo_count": len(memos),
            "extractor": "local heuristic parser; no ASR or LLM inference",
        },
        "metrics_definition": {
            "item_precision_recall": "one-to-one SKU/candidate matching over expected items",
            "quantity_accuracy": "correct quantities divided by expected items with known quantity; missing predictions count incorrect",
            "confident_wrong_rate": "incorrect confident lines divided by all confident lines",
            "flag_rate": "ambiguous and no-match lines divided by all predicted lines",
            "price_correctness": "confident line unit price and integer line total checked against catalog",
        },
        "variants": variants,
        "comparisons_not_measured": {
            "asr_hotwords_on_off": (
                "No local evaluation audio files are present."
                if audio_count == 0 else
                "Audio WER comparison is not implemented in this typed-phrase runner."
            ),
            "llm_models": "No model comparison dataset/runner is configured; no inference was run.",
        },
        "audio_files_available": audio_count,
        # Keep the seeded-alias metrics at top level for existing consumers.
        **with_aliases,
        "per_memo": [
            {
                "memo_id": result.memo_id,
                "recall": result.item_recall,
                "precision": result.item_precision,
                "quantity_accuracy": result.quantity_accuracy,
                "flag_rate": result.flag_rate,
                "confident_wrong": result.confident_wrong,
                "confident_wrong_count": result.confident_wrong_count,
                "confident_line_count": result.confident_line_count,
                "price_correct": result.price_correct,
                "predicted_lines": result.predicted_lines,
            }
            for result in results
        ],
    }

    output_path = Path(__file__).parent / "eval_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {output_path}")

    if with_aliases["confident_wrong_count"] > 0:
        print(
            f"\nConfident-wrong lines found: "
            f"{with_aliases['confident_wrong_count']}/"
            f"{with_aliases['confident_line_count']}"
        )
        sys.exit(1)


if __name__ == "__main__":
    run_evaluation()
