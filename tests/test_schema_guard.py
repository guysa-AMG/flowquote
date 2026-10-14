"""Schema guard test (PLAN.md §2, §7, AGENTS.md).

Hard non-negotiable rule:
Assert generated JSON schema contains NO property whose name includes
price, cost, amount, total, or currency.
Assert model output containing currency symbols is rejected.
"""
import pytest
from pydantic import ValidationError

from app.extract import Extraction, SpokenLine, get_extraction_schema

FORBIDDEN_TERMS = ["price", "cost", "amount", "total", "currency"]

def test_json_schema_has_zero_forbidden_price_fields():
    schema = get_extraction_schema()

    # Flatten all schema field names
    found_keys = []
    def extract_keys(d):
        if isinstance(d, dict):
            for k, v in d.items():
                found_keys.append(str(k).lower())
                extract_keys(v)
        elif isinstance(d, list):
            for item in d:
                extract_keys(item)

    extract_keys(schema)

    for key in found_keys:
        for forbidden in FORBIDDEN_TERMS:
            assert forbidden not in key, f"Forbidden term '{forbidden}' found in schema key: {key}"

def test_extraction_accepts_clean_spoken_line():
    extraction = Extraction(
        lines=[
            SpokenLine(
                spoken="replaced 15mm copper elbow",
                kind="part",
                quantity=2,
                unit="each",
            ),
            SpokenLine(
                spoken="two hours labour",
                kind="labour",
                quantity=2,
                unit="hours",
            ),
        ],
        customer_name="Mr Smith",
        site_address="14 Oak Road",
    )
    assert len(extraction.lines) == 2
    assert extraction.lines[0].kind == "part"
    assert extraction.lines[1].quantity == 2

@pytest.mark.parametrize("invalid_spoken", [
    "Replaced geyser element for R450",
    "Bought 2 copper pipes $50 each",
    "Callout fee £60",
    "Cost was 100€ total",
])
def test_extraction_rejects_currency_symbols_in_spoken(invalid_spoken: str):
    with pytest.raises(ValidationError):
        SpokenLine(
            spoken=invalid_spoken,
            kind="part",
        )
