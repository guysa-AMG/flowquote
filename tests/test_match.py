"""Matcher test suite covering known traps (PLAN.md §8)."""
import pytest

from app.match import (
    MatchOutcome,
    PriceItemCandidate,
    match_line,
)


@pytest.fixture
def sample_items():
    return [
        PriceItemCandidate(id=1, sku="COP-15-ELB", name="15mm Copper Elbow", unit="each", price_cents=1850, category="fittings", attrs={"material": "copper", "size": "15mm", "type": "elbow"}),
        PriceItemCandidate(id=2, sku="COP-22-ELB", name="22mm Copper Elbow", unit="each", price_cents=2950, category="fittings", attrs={"material": "copper", "size": "22mm", "type": "elbow"}),
        PriceItemCandidate(id=3, sku="PEX-15-ELB", name="15mm PEX Elbow Fitting", unit="each", price_cents=1600, category="fittings", attrs={"material": "pex", "size": "15mm", "type": "elbow"}),
        PriceItemCandidate(id=4, sku="LBR-PLM-STD", name="Plumbing Labour Standard (per hour)", unit="hours", price_cents=65000, category="labour", attrs={"kind": "labour"}),
    ]

def test_confident_match(sample_items):
    res = match_line("15mm copper elbow", sample_items)
    assert res.outcome == MatchOutcome.CONFIDENT
    assert res.best_match is not None
    assert res.best_match.sku == "COP-15-ELB"

def test_attribute_conflict_elimination(sample_items):
    # Spoken specifies 22mm, should eliminate 15mm items entirely
    res = match_line("22mm copper elbow", sample_items)
    assert res.outcome == MatchOutcome.CONFIDENT
    assert res.best_match is not None
    assert res.best_match.sku == "COP-22-ELB"

def test_ambiguous_unstated_size(sample_items):
    # Spoken says "copper elbow" without stating size. Both 15mm and 22mm exist.
    res = match_line("copper elbow", sample_items)
    assert res.outcome == MatchOutcome.AMBIGUOUS
    assert res.flag_reason is not None
    assert {candidate.item.sku for candidate in res.candidates} >= {
        "COP-15-ELB",
        "COP-22-ELB",
    }

def test_no_match_for_unknown_item(sample_items):
    res = match_line("flux capacitor valve", sample_items)
    assert res.outcome == MatchOutcome.NO_MATCH

def test_alias_resolution(sample_items):
    # 'geezer' maps to 'geyser' via alias table
    items = [
        PriceItemCandidate(id=10, sku="GEY-ELM-3KW", name="Geyser Element 3kW", unit="each", price_cents=32000, category="geyser", attrs={"type": "element"}),
    ]
    alias_map = {"geezer": "geyser"}
    res = match_line("geezer element", items, alias_map=alias_map)
    assert res.outcome == MatchOutcome.CONFIDENT
    assert res.best_match.sku == "GEY-ELM-3KW"


def test_unspecified_labour_rate_is_ambiguous():
    items = [
        PriceItemCandidate(
            id=40,
            sku="LBR-PLM-STD",
            name="Plumbing Labour Standard (per hour)",
            unit="hours",
            price_cents=65000,
            category="labour",
            attrs={"kind": "labour", "rate": "standard"},
        ),
        PriceItemCandidate(
            id=41,
            sku="LBR-PLM-AFT",
            name="Plumbing Labour After Hours (per hour)",
            unit="hours",
            price_cents=95000,
            category="labour",
            attrs={"kind": "labour", "rate": "after_hours"},
        ),
    ]

    result = match_line("two hours labour", items)

    assert result.outcome == MatchOutcome.AMBIGUOUS
    assert {candidate.item.sku for candidate in result.candidates} == {
        "LBR-PLM-STD",
        "LBR-PLM-AFT",
    }


def test_explicit_after_hours_labour_rate_is_confident():
    items = [
        PriceItemCandidate(
            id=40,
            sku="LBR-PLM-STD",
            name="Plumbing Labour Standard (per hour)",
            unit="hours",
            price_cents=65000,
            category="labour",
            attrs={"kind": "labour", "rate": "standard"},
        ),
        PriceItemCandidate(
            id=41,
            sku="LBR-PLM-AFT",
            name="Plumbing Labour After Hours (per hour)",
            unit="hours",
            price_cents=95000,
            category="labour",
            attrs={"kind": "labour", "rate": "after_hours"},
        ),
    ]

    result = match_line("after hours labour 2 hours", items)

    assert result.outcome == MatchOutcome.CONFIDENT
    assert result.best_match is not None
    assert result.best_match.sku == "LBR-PLM-AFT"


def test_callout_phrase_does_not_trigger_labour_rate_ambiguity():
    items = [
        PriceItemCandidate(
            id=40,
            sku="LBR-PLM-STD",
            name="Plumbing Labour Standard (per hour)",
            unit="hours",
            price_cents=65000,
            category="labour",
            attrs={"kind": "labour", "rate": "standard"},
        ),
        PriceItemCandidate(
            id=41,
            sku="LBR-PLM-AFT",
            name="Plumbing Labour After Hours (per hour)",
            unit="hours",
            price_cents=95000,
            category="labour",
            attrs={"kind": "labour", "rate": "after_hours"},
        ),
        PriceItemCandidate(
            id=42,
            sku="FEE-CALLOUT",
            name="Standard Call-out and Diagnostic Fee",
            unit="each",
            price_cents=55000,
            category="callout",
            attrs={"kind": "callout"},
        ),
    ]

    result = match_line(
        "callout fee",
        items,
        alias_map={"callout fee": "Standard Call-out and Diagnostic Fee"},
    )

    assert result.outcome == MatchOutcome.CONFIDENT
    assert result.best_match is not None
    assert result.best_match.sku == "FEE-CALLOUT"
