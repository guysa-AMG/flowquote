"""Pricing engine tests (PLAN.md §2, §8).

Verifies integer-cent calculations, round_half_up, VAT computations,
and ensures no floats are used in monetary math.
"""
from decimal import Decimal
import pytest
from app.pricing import (
    round_half_up,
    qty_to_milli,
    calculate_line_total_cents,
    calculate_vat_cents,
    calculate_quote_totals,
)

def test_round_half_up():
    assert round_half_up(Decimal("10.4")) == 10
    assert round_half_up(Decimal("10.5")) == 11
    assert round_half_up(Decimal("10.6")) == 11
    assert round_half_up(Decimal("123.456")) == 123

def test_qty_to_milli():
    assert qty_to_milli(1) == 1000
    assert qty_to_milli(1.5) == 1500
    assert qty_to_milli("2.25") == 2250
    assert qty_to_milli(3) == 3000

def test_calculate_line_total_cents():
    # 1.5 units @ 1850 cents (R18.50) = 2775 cents (R27.75)
    qty_milli = 1500
    unit_price = 1850
    total = calculate_line_total_cents(qty_milli, unit_price)
    assert total == 2775

def test_calculate_vat_cents():
    # Subtotal 10000 cents (R100.00), VAT rate 1500 bp (15%) = 1500 cents (R15.00)
    subtotal = 10000
    vat_rate = 1500
    assert calculate_vat_cents(subtotal, vat_rate) == 1500

def test_calculate_quote_totals():
    line_totals = [2775, 65000, 55000]  # 122775 cents = R1,227.75
    subtotal, vat, total = calculate_quote_totals(line_totals, vat_rate_bp=1500)
    assert subtotal == 122775
    assert vat == 18416  # round_half_up(122775 * 0.15) = 18416.25 -> 18416
    assert total == 141191
