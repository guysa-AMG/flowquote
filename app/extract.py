"""Extraction schema and validator for LLM output.

Core rule (PLAN.md §2, §7):
The model extracts what was said. It has NO price, cost, amount, total, or currency field.
Any currency symbol in model output is rejected.
"""
import json
import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.config import settings

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
            escaped = re.escape(sym)
            if re.search(rf"{escaped}\s*\d+", v) or re.search(rf"\d+\s*{escaped}", v):
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


async def extract_with_llm(transcript: str) -> Extraction:
    """
    Call Ollama with structured output to extract structured lines from transcript.
    Uses temperature=0, thinking off, and the Pydantic JSON schema.
    """
    import ollama

    schema = get_extraction_schema()

    system_prompt = (
        "You are a precise extraction engine for plumbing voice memos.\n"
        "Extract ONLY what was explicitly said. Do not infer items not mentioned. "
        "Do not guess quantities.\n"
        'Mark vague quantities (e.g. "a couple", "a few", "some") with '
        "quantity_vague=true.\n"
        "Never add prices, costs, amounts, totals, or currency. "
        "The output schema forbids these fields."
    )

    user_prompt = f"""Transcript: "{transcript}"

Extract each distinct item mentioned as a separate line with:
- spoken: the exact phrase for this item
- kind: "part" | "labour" | "callout" | "other"
- quantity: numeric value if stated, otherwise null
- quantity_vague: true if vague quantity words used
- unit: "each" | "m" | "hours" | etc if stated
- refers_to_previous: reference like "the Smith job" if mentioned

Also extract customer_name and site_address if mentioned."""

    client = ollama.AsyncClient(host=settings.ollama_host)

    # Retry once if currency symbols appear in output
    for attempt in range(2):
        try:
            response = await client.chat(
                model=settings.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                format=schema,
                options={
                    "temperature": 0,
                    "num_predict": 512,
                },
            )

            content = response["message"]["content"]
            extraction = Extraction.model_validate_json(content)

            # Verify no currency symbols in spoken fields (defense in depth)
            for line in extraction.lines:
                for sym in CURRENCY_SYMBOLS:
                    if sym in line.spoken:
                        raise ValueError(f"Currency symbol {sym} in extraction output")

            return extraction

        except (json.JSONDecodeError, ValueError) as e:
            if attempt == 0:
                # Retry once with a stricter reminder
                user_prompt += (
                    "\n\nIMPORTANT: Output MUST conform to the JSON schema. "
                    "No currency symbols. No price fields."
                )
                continue
            raise RuntimeError(f"LLM extraction failed after retry: {e}") from e

    raise RuntimeError("LLM extraction failed")
