"""Deterministic pricing calculation engine.

Non-negotiable rules (PLAN.md §2, §8):
- All money is stored and calculated in integer cents.
- Quantities are stored as integer thousandths (quantity_milli: 1.5 units -> 1500 milliunits).
- line_total = round_half_up(quantity * unit_price)
- subtotal = sum(lines)
- vat = round_half_up(subtotal * vat_rate_bp / 10000)
- total = subtotal + vat
- Never use floats for monetary calculation.
"""
from decimal import Decimal, ROUND_HALF_UP

MILLI_FACTOR = Decimal(1000)
BP_FACTOR = Decimal(10000)

def round_half_up(val: Decimal) -> int:
    """Rounds a Decimal to nearest integer using standard half-up arithmetic."""
    return int(val.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def qty_to_milli(quantity: Decimal | float | int | str) -> int:
    """Converts a user-provided numeric quantity into integer thousandths."""
    d = Decimal(str(quantity))
    return int((d * MILLI_FACTOR).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def milli_to_decimal(quantity_milli: int) -> Decimal:
    """Converts thousandths back into Decimal units."""
    return Decimal(quantity_milli) / MILLI_FACTOR

def calculate_line_total_cents(quantity_milli: int, unit_price_cents: int) -> int:
    """
    Computes line total in integer cents.
    line_total = round_half_up((quantity_milli / 1000) * unit_price_cents)
    """
    qty_dec = Decimal(quantity_milli) / MILLI_FACTOR
    total_dec = qty_dec * Decimal(unit_price_cents)
    return round_half_up(total_dec)

def calculate_vat_cents(subtotal_cents: int, vat_rate_bp: int) -> int:
    """
    Computes VAT in integer cents.
    vat = round_half_up(subtotal_cents * vat_rate_bp / 10000)
    """
    vat_dec = (Decimal(subtotal_cents) * Decimal(vat_rate_bp)) / BP_FACTOR
    return round_half_up(vat_dec)

def calculate_quote_totals(line_totals_cents: list[int], vat_rate_bp: int) -> tuple[int, int, int]:
    """
    Calculates (subtotal_cents, vat_cents, total_cents) from a list of line totals.
    """
    subtotal_cents = sum(line_totals_cents)
    vat_cents = calculate_vat_cents(subtotal_cents, vat_rate_bp)
    total_cents = subtotal_cents + vat_cents
    return subtotal_cents, vat_cents, total_cents

def format_cents_to_display(cents: int, currency: str = "ZAR") -> str:
    """Formats integer cents as standard currency string with 2 decimal places."""
    dollars = Decimal(cents) / Decimal(100)
    return f"{currency} {dollars:.2f}"
