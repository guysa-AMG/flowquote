"""No network test (PLAN.md §3).

Asserts that running pipeline operations does not attempt outbound network sockets.
"""
import pytest

from app.match import PriceItemCandidate, match_line
from app.pricing import calculate_line_total_cents


@pytest.mark.usefixtures("disable_socket")
def test_pipeline_functions_without_network():
    # Verify pure functions execute offline without raising socket errors
    line_total = calculate_line_total_cents(1500, 1850)
    assert line_total == 2775

    items = [
        PriceItemCandidate(id=1, sku="COP-15-ELB", name="15mm Copper Elbow", unit="each", price_cents=1850, category="fittings", attrs={"size": "15mm"})
    ]
    res = match_line("15mm copper elbow", items)
    assert res.outcome.value == "confident"
