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
# Match mm, mm², inch, " or in
SIZE_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(mm²?|inch|\"|in)\b", re.IGNORECASE
)
MATERIAL_PATTERN = re.compile(
    r"\b(copper|pex|pvc|poly|brass|galvanised|galvanized|pvc-u)\b", re.IGNORECASE
)
FITTING_TYPE_PATTERN = re.compile(
    r"\b(elbow|tee|coupler|coupling|valve|bushing|nipple|"
    r"union|adaptor|adapter|trap|socket)\b",
    re.IGNORECASE,
)
LABOUR_RATE_CONTEXT_PATTERN = re.compile(
    r"\b(labour|labor|hour|hours)\b", re.IGNORECASE
)


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

    if re.search(
        r"\b(?:after[\s-]+hours?|overtime|out[\s-]+of[\s-]+hours?)\b",
        text,
        re.IGNORECASE,
    ):
        attrs["rate"] = "after_hours"
    elif re.search(r"\b(?:standard|normal|regular)\b", text, re.IGNORECASE):
        attrs["rate"] = "standard"

    return attrs


def _canon_size(v: str) -> str:
    """Normalize size strings: 1.5mm² / 1.5mm² / 1.5mm all canonicalize so
    that a casual '1.5mm' spoken size does not conflict with the stocked
    '1.5mm²' cable item (and vice-versa)."""
    s = v.strip().lower()
    # Strip a trailing superscript-2 to unify mm vs mm² when compared.
    return s.replace("mm²", "mm").replace("mm2", "mm")


def attributes_conflict(
    spoken_attrs: dict[str, str], candidate_attrs: dict[str, str]
) -> bool:
    """Returns True if any explicit spoken attribute directly contradicts candidate attribute."""
    for key, val in spoken_attrs.items():
        cand_val = candidate_attrs.get(key)
        if cand_val and cand_val != val:
            if key == "size" and _canon_size(val) == _canon_size(cand_val):
                continue
            return True
    return False


def _score_candidate(spoken: str, item: PriceItemCandidate) -> float:
    token_score = fuzz.token_set_ratio(spoken, item.name.lower())
    partial_score = fuzz.partial_ratio(spoken, item.name.lower())
    return (token_score * 0.6) + (partial_score * 0.4)


def apply_aliases(text: str, alias_map: dict[str, str]) -> str:
    """Substitutes trade slang and known speech-to-text slips (e.g. geezer -> geyser).

    Single-pass, longest-match-first to avoid partial matches (e.g. "labour"
    re-matching inside an already-substituted price item name).
    """
    if not alias_map:
        return text.lower()

    # Build a single alternation regex, longest phrases first so "after hours labour"
    # wins over the bare "hours" entry.
    phrases = sorted({str(p) for p in alias_map.keys() if p}, key=len, reverse=True)
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(str(p).lower()) for p in phrases) + r")\b"
    )

    # Lookup by case-insensitive key.
    lookup = {str(k).lower(): v for k, v in alias_map.items()}

    def replacer(match: re.Match) -> str:
        return lookup.get(match.group(1).lower(), match.group(0))

    return pattern.sub(replacer, text.lower())

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
        final_score = _score_candidate(normalized_spoken, item)
        if final_score >= min_score:
            scored.append(ScoredCandidate(item=item, score=final_score))

    scored.sort(key=lambda s: s.score, reverse=True)

    has_labour_context = (
        LABOUR_RATE_CONTEXT_PATTERN.search(normalized_spoken) is not None
    )
    has_specific_rate = re.search(
        r"\b(?:standard|normal|regular|after[\s-]+hours?|overtime|"
        r"out[\s-]+of[\s-]+hours?)\b",
        normalized_spoken,
    ) is not None
    labour_items = [item for item in survivors if item.category.lower() == "labour"]
    labour_rates = {
        (item.attrs or {}).get("rate")
        for item in labour_items
        if (item.attrs or {}).get("rate")
    }
    if has_labour_context and not has_specific_rate and len(labour_rates) > 1:
        labour_candidates = [
            ScoredCandidate(item=item, score=_score_candidate(normalized_spoken, item))
            for item in labour_items
        ]
        labour_candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        return MatchResult(
            spoken=spoken,
            outcome=MatchOutcome.AMBIGUOUS,
            best_match=labour_candidates[0].item,
            best_score=labour_candidates[0].score,
            candidates=labour_candidates[:5],
            flag_reason="Unstated labour rate: standard and after-hours prices differ",
        )

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
        # E.g., user said "copper elbow" and didn't state size, but other copper
        # elbows exist in price list
        if "size" not in spoken_attrs:
            best_attrs = best.item.attrs or parse_attributes(best.item.name)
            if "size" in best_attrs:
                sister_sizes = []
                for other in survivors:
                    other_attrs = other.attrs or parse_attributes(other.name)
                    if other.id == best.item.id or other_attrs.get("size") == best_attrs["size"]:
                        continue
                    shared_attrs = [
                        key
                        for key in ("material", "type")
                        if best_attrs.get(key) is not None
                    ]
                    if shared_attrs and all(
                        other_attrs.get(key) == best_attrs[key] for key in shared_attrs
                    ):
                        sister_sizes.append(
                            ScoredCandidate(
                                item=other,
                                score=_score_candidate(normalized_spoken, other),
                            )
                        )
                if sister_sizes:
                    size_candidates = sorted(
                        [*scored, *sister_sizes],
                        key=lambda candidate: candidate.score,
                        reverse=True,
                    )
                    return MatchResult(
                        spoken=spoken,
                        outcome=MatchOutcome.AMBIGUOUS,
                        best_match=best.item,
                        best_score=best.score,
                        candidates=size_candidates[:5],
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
