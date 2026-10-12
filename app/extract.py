"""Extraction schema and validator for LLM output.

Core rule (PLAN.md §2, §7):
The model extracts what was said. It has NO price, cost, amount, total, or currency field.
Any currency symbol in model output is rejected.
"""
from decimal import Decimal
import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator

CURRENCY_SYMBOLS = ["$", "£", "€", "R", "¥", "₹"]
FORBIDDEN_PRICE_TERMS = ["price", "cost", "amount", "total", "currency"]

class SpokenLine(BaseModel):
    spoken: str = Field(description="The item exactly as the plumber said it")
    kind: Literal["part", "labour", "callout", "other"]
    quantity: Decimal | None = Field(None, description="Numeric quantity if stated")
    quantity_vague: bool = Field(False, description="True for 'a couple', 'a few', 'some'")
    unit: str | None = None  # each, m, hours, ...
    refers_to_previous: str | None = None  # e.g. "the Smith job"

    @field_validator("spoken")
    @classmethod
    def reject_currency_symbols(cls, v: str) -> str:
        for sym in CURRENCY_SYMBOLS:
            # Check for currency symbols with numbers, e.g. $50, R150, £20
            if re.search(rf"\{sym}\s*\d+", v) or re.search(rf"\d+\s*\{sym}", v):
                raise ValueError(f"Spoken text contains illegal currency symbol: {sym}")
        return v

class Extraction(BaseModel):
    lines: list[SpokenLine]
    customer_name: str | None = None
    site_address: str | None = None

def get_extraction_schema() -> dict:
    """Return JSON schema and verify absence of price/cost fields."""
    schema = Extraction.model_json_schema()
    _verify_no_price_in_schema(schema)
    return schema

def _verify_no_price_in_schema(schema: dict) -> None:
    """Recursively verify no price/amount field in schema definition."""
    def check_dict(d: dict):
        for k, v in d.items():
            k_lower = str(k).lower()
            for term in FORBIDDEN_PRICE_TERMS:
                if term in k_lower:
                    raise AssertionError(f"Forbidden price field '{k}' detected in LLM schema!")
            if isinstance(v, dict):
                check_dict(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        check_dict(item)

    check_dict(schema.get("properties", {}))
    for defn in schema.get("$defs", {}).values():
        if isinstance(defn, dict):
            check_dict(defn.get("properties", {}))
