from app.tracing import local_stage


def test_local_stage_emits_duration_without_customer_payload(caplog):
    private_text = "customer name and address"

    with caplog.at_level("INFO", logger="talkquote.pipeline"):
        with local_stage("review_resolution"):
            _ = private_text

    record = next(record for record in caplog.records if record.name == "talkquote.pipeline")
    assert record.stage == "review_resolution"
    assert isinstance(record.duration_ms, float)
    assert private_text not in record.getMessage()
