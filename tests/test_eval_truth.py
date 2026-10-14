import json
from pathlib import Path


def test_eval_truth_records_have_required_fields_and_integer_quantities():
    truth_path = Path(__file__).parents[1] / "eval" / "truth.jsonl"
    records = [
        json.loads(line)
        for line in truth_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert records

    for record in records:
        assert record["memo_id"]
        assert record["transcript"].strip()
        assert isinstance(record["expected_items"], list)
        for item in record["expected_items"]:
            assert item["sku"]
            assert isinstance(item["quantity_milli"], int)
