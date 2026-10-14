from app.match import PriceItemCandidate
from eval.run_eval import evaluate_memo, extract_lines_local, match_lines


def test_vague_quantity_is_flagged_and_not_priced():
    items = [
        PriceItemCandidate(
            id=1,
            sku="COP-15-PIP",
            name="15mm Copper Pipe",
            unit="each",
            price_cents=29500,
            category="pipe",
            attrs={"material": "copper", "size": "15mm", "type": "pipe"},
        )
    ]
    line = extract_lines_local("some 15mm copper pipe")[0]

    prediction = match_lines([line], items, {})[0]

    assert line.quantity_vague
    assert prediction["quantity_milli"] == 0
    assert prediction["match_outcome"] == "ambiguous"
    assert prediction["unit_price_cents"] == 0
    assert prediction["line_total_cents"] == 0


def test_duplicate_predictions_do_not_collapse_and_count_as_confident_wrong():
    item = PriceItemCandidate(
        id=1,
        sku="COP-15-ELB",
        name="15mm Copper Elbow",
        unit="each",
        price_cents=1850,
        category="fittings",
        attrs={"material": "copper", "size": "15mm", "type": "elbow"},
    )

    result = evaluate_memo(
        "duplicate",
        "15mm copper elbow and 15mm copper elbow",
        [{"sku": "COP-15-ELB", "quantity_milli": 1000}],
        [item],
        {},
    )

    assert len(result.predicted_lines) == 2
    assert result.item_precision == 0.5
    assert not result.confident_wrong
    assert result.confident_wrong_count == 0


def test_confidently_selected_unexpected_sku_is_counted_wrong():
    items = [
        PriceItemCandidate(
            id=1,
            sku="COP-15-ELB",
            name="15mm Copper Elbow",
            unit="each",
            price_cents=1850,
            category="fittings",
            attrs={"material": "copper", "size": "15mm", "type": "elbow"},
        ),
        PriceItemCandidate(
            id=2,
            sku="PEX-15-ELB",
            name="15mm PEX Elbow Fitting",
            unit="each",
            price_cents=1600,
            category="fittings",
            attrs={"material": "pex", "size": "15mm", "type": "elbow"},
        ),
    ]

    result = evaluate_memo(
        "wrong-sku",
        "15mm PEX elbow",
        [{"sku": "COP-15-ELB", "quantity_milli": 1000}],
        items,
        {},
    )

    assert result.confident_wrong
    assert result.confident_wrong_count == 1


def test_missing_expected_item_counts_against_quantity_accuracy():
    item = PriceItemCandidate(
        id=1,
        sku="COP-15-ELB",
        name="15mm Copper Elbow",
        unit="each",
        price_cents=1850,
        category="fittings",
        attrs={"material": "copper", "size": "15mm", "type": "elbow"},
    )

    result = evaluate_memo(
        "missed-item",
        "15mm copper elbow and 22mm copper tee",
        [
            {"sku": "COP-15-ELB", "quantity_milli": 1000},
            {"sku": "COP-22-TEE", "quantity_milli": 1000},
        ],
        [item],
        {},
    )

    assert result.item_recall == 0.5
    assert result.quantity_accuracy == 0.5


def test_unknown_quantity_is_excluded_from_quantity_accuracy():
    result_expected = [{"sku": "COP-15-PIP", "quantity_milli": None}]
    item = PriceItemCandidate(
        id=1,
        sku="COP-15-PIP",
        name="15mm Copper Pipe",
        unit="each",
        price_cents=29500,
        category="pipe",
        attrs={"material": "copper", "size": "15mm", "type": "pipe"},
    )
    result = evaluate_memo(
        "vague",
        "some 15mm copper pipe",
        result_expected,
        [item],
        {},
    )

    assert result.quantity_accuracy == 1.0
    assert result.flag_rate == 1.0


def test_seeded_generic_hour_aliases_do_not_override_after_hours_phrase(
    tmp_path, monkeypatch
):
    from app.config import settings
    from app.db import get_db, init_db, seed_default_aliases
    from eval.run_eval import load_price_items_and_aliases

    monkeypatch.setattr(settings, "database_path", str(tmp_path / "matcher.sqlite"))
    init_db()
    with get_db() as conn:
        labour = conn.execute(
            """SELECT id FROM price_item
               WHERE business_id = 'biz_default' AND category = 'labour' LIMIT 1"""
        ).fetchone()
        conn.execute(
            """INSERT INTO alias (business_id, phrase, price_item_id, source)
               VALUES ('biz_default', 'hours', ?, 'seed')""",
            (labour["id"],),
        )
        conn.execute(
            """INSERT INTO alias (business_id, phrase, price_item_id, source)
               VALUES ('biz_default', 'hours', ?, 'learned')""",
            (labour["id"],),
        )
        seed_default_aliases(conn)
        sources = conn.execute(
            "SELECT source FROM alias WHERE business_id = 'biz_default' AND phrase = 'hours'"
        ).fetchall()
        conn.execute(
            "DELETE FROM alias WHERE business_id = 'biz_default' AND phrase = 'hours'"
        )
    assert [row["source"] for row in sources] == ["learned"]

    items, aliases = load_price_items_and_aliases()

    assert "hour" not in aliases
    assert "hours" not in aliases
    result = evaluate_memo(
        "after-hours",
        "after hours labour 2 hours",
        [{"sku": "LBR-PLM-AFT", "quantity_milli": 2000}],
        items,
        aliases,
    )
    confident_lines = [
        line for line in result.predicted_lines if line["match_outcome"] == "confident"
    ]

    assert len(confident_lines) == 1
    assert confident_lines[0]["matched_sku"] == "LBR-PLM-AFT"
