"""Two-stage attribute parsing and fuzzy matching engine.

Matching rules (PLAN.md §8):
1. Attribute parsing: regex extracts attributes (size, material, type, rating).
   Candidates that conflict with explicit attributes are eliminated.
2. Ranking: RapidFuzz scores surviving candidates, augmented by an alias table.
3. Three outcomes:
   - CONFIDENT: exactly 1 survivor > MIN_SCORE and margin over runner-up > MIN_MARGIN.
   - AMBIGUOUS: multiple survivors, or unstated attribute differs (e.g. 15mm vs 22mm).
   - NO_MATCH: nothing above MIN_SCORE. Never guess.
"""
import re
from dataclasses import dataclass, field
from enum import StrEnum

from rapidfuzz import fuzz

from app.config import settings


class MatchOutcome(StrEnum):
    CONFIDENT = "confident"
    AMBIGUOUS = "ambiguous"
    NO_MATCH = "no_match"

@dataclass
class PriceItemCandidate:
    id: int
    sku: str
    name: str
    unit: str
    price_cents: int
    category: str
    attrs: dict[str, str] = field(default_factory=dict)

@dataclass
class ScoredCandidate:
    item: PriceItemCandidate
    score: float
    reason: str = ""

@dataclass
class MatchResult:
    spoken: str
    outcome: MatchOutcome
    best_match: PriceItemCandidate | None = None
    best_score: float = 0.0
    candidates: list[ScoredCandidate] = field(default_factory=list)
    flag_reason: str | None = None

# Regex patterns for common plumbing attributes
SIZE_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\s*(mm|inch|\"|in|mm²)\b", re.IGNORECASE)
MATERIAL_PATTERN = re.compile(r"\b(copper|pex|pvc|poly|brass|galvanised|galvanized|pvc-u)\b", re.IGNORECASE)
FITTING_TYPE_PATTERN = re.compile(r"\b(elbow|tee|coupler|coupling|valve|bushing|nipple|union|adaptor|adapter|trap|socket)\b", re.IGNORECASE)
KIND_LABOUR_PATTERN = re.compile(r"\b(labour|labor|hour|hours|callout|call-out|trip)\b", re.IGNORECASE)

def parse_attributes(text: str) -> dict[str, str]:
    """Extracts explicit attributes like size, material, and fitting type from string."""
    attrs: dict[str, str] = {}

    # Size
    size_match = SIZE_PATTERN.search(text)
    if size_match:
        size_val = size_match.group(1)
        unit = size_match.group(2).lower()
        if unit in ['"', "in"]:
            unit = "inch"
        attrs["size"] = f"{size_val}{unit}"

    # Material
    mat_match = MATERIAL_PATTERN.search(text)
    if mat_match:
        attrs["material"] = mat_match.group(1).lower()

    # Type
    type_match = FITTING_TYPE_PATTERN.search(text)
    if type_match:
        attrs["type"] = type_match.group(1).lower()

    return attrs

def attributes_conflict(spoken_attrs: dict[str, str], candidate_attrs: dict[str, str]) -> bool:
    """Returns True if any explicit spoken attribute directly contradicts candidate attribute."""
    for key, val in spoken_attrs.items():
        cand_val = candidate_attrs.get(key)
        if cand_val and cand_val != val:
            return True
    return False

def apply_aliases(text: str, alias_map: dict[str, str]) -> str:
    """Substitutes trade slang and known speech-to-text slips (e.g. geezer -> geyser)."""
    norm = text.lower()
    for slang, standard in alias_map.items():
        norm = re.sub(rf"\b{re.escape(slang.lower())}\b", standard, norm)
    return norm

def match_line(
    spoken: str,
    price_items: list[PriceItemCandidate],
    alias_map: dict[str, str] | None = None,
    min_score: float | None = None,
    min_margin: float | None = None,
) -> MatchResult:
    """
    Executes two-stage matching: attribute filtering followed by RapidFuzz ranking.
    """
    min_score = min_score if min_score is not None else settings.min_score
    min_margin = min_margin if min_margin is not None else settings.min_margin
    alias_map = alias_map or {}

    normalized_spoken = apply_aliases(spoken, alias_map)
    spoken_attrs = parse_attributes(normalized_spoken)

    # 1. Attribute filtering
    survivors: list[PriceItemCandidate] = []
    for item in price_items:
        item_attrs = item.attrs or parse_attributes(item.name)
        if attributes_conflict(spoken_attrs, item_attrs):
            continue
        survivors.append(item)

    if not survivors:
        return MatchResult(
            spoken=spoken,
            outcome=MatchOutcome.NO_MATCH,
            flag_reason="Attributes conflict with all available items",
        )

    # 2. Score survivors with RapidFuzz
    scored: list[ScoredCandidate] = []
    for item in survivors:
        # Compare normalized spoken with item name
        token_score = fuzz.token_set_ratio(normalized_spoken, item.name.lower())
        partial_score = fuzz.partial_ratio(normalized_spoken, item.name.lower())
        final_score = (token_score * 0.6) + (partial_score * 0.4)

        if final_score >= min_score:
            scored.append(ScoredCandidate(item=item, score=final_score))

    scored.sort(key=lambda s: s.score, reverse=True)

    # 3. Determine outcome
    if not scored:
        return MatchResult(
            spoken=spoken,
            outcome=MatchOutcome.NO_MATCH,
            flag_reason=f"No matching item exceeded score threshold {min_score}",
        )

    best = scored[0]

    # Check if multiple candidates exist
    if len(scored) == 1:
        # Check if an unstated critical attribute (like size) could cause ambiguity
        # E.g., user said "copper elbow" and didn't state size, but other copper elbows exist in price list
        if "size" not in spoken_attrs:
            # Check if other items in price_items share the same material and type with different sizes
            best_attrs = best.item.attrs or parse_attributes(best.item.name)
            if "size" in best_attrs:
                has_sister_sizes = any(
                    other.id != best.item.id
                    and (other.attrs.get("material") or parse_attributes(other.name).get("material")) == best_attrs.get("material")
                    and (other.attrs.get("type") or parse_attributes(other.name).get("type")) == best_attrs.get("type")
                    for other in price_items
                )
                if has_sister_sizes:
                    return MatchResult(
                        spoken=spoken,
                        outcome=MatchOutcome.AMBIGUOUS,
                        best_match=best.item,
                        best_score=best.score,
                        candidates=scored,
                        flag_reason="Unstated size attribute: multiple sizes available",
                    )

        return MatchResult(
            spoken=spoken,
            outcome=MatchOutcome.CONFIDENT,
            best_match=best.item,
            best_score=best.score,
            candidates=scored,
        )

    runner_up = scored[1]
    margin = best.score - runner_up.score

    if margin < min_margin:
        return MatchResult(
            spoken=spoken,
            outcome=MatchOutcome.AMBIGUOUS,
            best_match=best.item,
            best_score=best.score,
            candidates=scored[:5],
            flag_reason=f"Margin {margin:.1f} below threshold {min_margin}",
        )

    return MatchResult(
        spoken=spoken,
        outcome=MatchOutcome.CONFIDENT,
        best_match=best.item,
        best_score=best.score,
        candidates=scored[:5],
    )
