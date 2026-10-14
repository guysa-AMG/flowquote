"""SQLite-backed async job processor (PLAN.md §6).

Processes memo jobs sequentially without external brokers (no Celery/Redis).
"""
import asyncio
import json
import logging
import tempfile
import uuid
from collections.abc import Callable, Coroutine
from decimal import Decimal
from pathlib import Path

from app.asr import Transcriber, normalize_audio_to_wav
from app.audit import log_audit_event
from app.config import settings
from app.db import fetch_price_items, get_db, seed_default_price_items
from app.extract import Extraction, extract_with_llm
from app.match import MatchOutcome, PriceItemCandidate, match_line
from app.pricing import (
    calculate_line_total_cents,
    calculate_quote_totals,
    qty_to_milli,
)

logger = logging.getLogger(__name__)


def _coerce_price_items(raw_items: list[dict]) -> list[PriceItemCandidate]:
    return [
        PriceItemCandidate(
            id=item["id"],
            sku=item["sku"],
            name=item["name"],
            unit=item["unit"],
            price_cents=item["price_cents"],
            category=item["category"],
            attrs=item.get("attrs", {}) or {},
        )
        for item in raw_items
    ]


def _quantity_to_milli(
    quantity: Decimal | float | int | None, quantity_vague: bool
) -> int:
    """Convert quantity to milliunits. Defaults to 1000 (1.0) if None."""
    if quantity is None:
        return 1000
    return qty_to_milli(quantity)


def build_quote_lines_from_extraction(
    extraction: Extraction, business_id: str = "biz_default"
) -> tuple[list[dict], list[dict]]:
    """Create quote lines from an LLM extraction by matching each line to price items."""
    with get_db() as conn:
        seed_default_price_items(conn, business_id=business_id)
        raw_items = fetch_price_items(conn, business_id=business_id)
    items = _coerce_price_items(raw_items)

    extracted_lines: list[dict] = []
    quote_lines: list[dict] = []

    for line in extraction.lines:
        # Match the spoken phrase against price items
        result = match_line(line.spoken, items)
        quantity_milli = (
            0
            if line.quantity_vague
            else _quantity_to_milli(line.quantity, line.quantity_vague)
        )
        if (
            result.best_match is not None
            and result.outcome == MatchOutcome.CONFIDENT
            and not line.quantity_vague
        ):
            unit_price = result.best_match.price_cents
            total_cents = calculate_line_total_cents(quantity_milli, unit_price)
            is_priceable = True
        else:
            unit_price = 0
            total_cents = 0
            is_priceable = False

        # Determine kind from LLM extraction (more reliable than keyword matching)
        kind = line.kind

        extracted_lines.append({
            "spoken": line.spoken,
            "kind": kind,
            "quantity": float(line.quantity) if line.quantity is not None else None,
            "quantity_vague": line.quantity_vague,
            "unit": line.unit or (result.best_match.unit if result.best_match else None),
            "refers_to_previous": line.refers_to_previous,
            "outcome": "ambiguous" if line.quantity_vague else result.outcome.value,
            "match_score": result.best_score,
        })

        quote_lines.append({
            "spoken": line.spoken,
            "price_item_id": result.best_match.id if is_priceable else None,
            "quantity_milli": quantity_milli,
            "unit": line.unit or (result.best_match.unit if result.best_match else None),
            "unit_price_cents": unit_price,
            "match_outcome": "ambiguous" if line.quantity_vague else result.outcome.value,
            "match_score": result.best_score,
            "resolved_by": "auto",
            "note": (
                "Confirm the vague quantity and select a price-list item"
                if line.quantity_vague
                else result.flag_reason
            ),
            "line_total_cents": total_cents,
            "kind": kind,
            "refers_to_previous": line.refers_to_previous,
        })

    return extracted_lines, quote_lines


def persist_quote_from_extraction(
    memo_id: str, extraction: Extraction, business_id: str = "biz_default"
) -> dict:
    """Persist a draft quote and quote version derived from an LLM extraction to SQLite."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memo WHERE id = ?", (memo_id,))
        memo_row = cursor.fetchone()
        if memo_row is None:
            raise ValueError(f"Memo {memo_id} not found")

        quote_id = memo_row["quote_id"] or f"quote_{uuid.uuid4().hex[:12]}"
        if memo_row["quote_id"] is None:
            cursor.execute(
                """INSERT INTO quote (id, business_id, number, customer_name, site_address, status)
                   VALUES (?, ?, ?, ?, ?, 'draft')""",
                (
                    quote_id,
                    business_id,
                    f"Q-{uuid.uuid4().hex[:8].upper()}",
                    extraction.customer_name,
                    extraction.site_address,
                ),
            )
            cursor.execute("UPDATE memo SET quote_id = ? WHERE id = ?", (quote_id, memo_id))
        else:
            # Update customer/site if extraction found them
            if extraction.customer_name or extraction.site_address:
                cursor.execute(
                    "UPDATE quote SET customer_name = COALESCE(?, customer_name), "
                    "site_address = COALESCE(?, site_address) WHERE id = ?",
                    (extraction.customer_name, extraction.site_address, quote_id),
                )

        extracted_lines, quote_lines = build_quote_lines_from_extraction(
            extraction, business_id=business_id
        )

        line_totals = [item["line_total_cents"] for item in quote_lines]
        subtotal_cents, vat_cents, total_cents = calculate_quote_totals(
            line_totals or [0], vat_rate_bp=settings.default_vat_rate_bp
        )
        version_id = f"qv_{uuid.uuid4().hex[:12]}"
        cursor.execute(
            """
            INSERT INTO quote_version (id, quote_id, version,
               subtotal_cents, vat_cents, total_cents)
            VALUES (?, ?, 1, ?, ?, ?)
            """,
            (version_id, quote_id, subtotal_cents, vat_cents, total_cents),
        )

        for line in quote_lines:
            cursor.execute(
                """
                INSERT INTO quote_line (
                    id, version_id, kind, spoken, price_item_id, quantity_milli, unit,
                    unit_price_cents, match_outcome, match_score, resolved_by, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"line_{uuid.uuid4().hex[:12]}",
                    version_id,
                    line["kind"],
                    line["spoken"],
                    line["price_item_id"],
                    line["quantity_milli"],
                    line["unit"],
                    line["unit_price_cents"],
                    line["match_outcome"],
                    line["match_score"],
                    line["resolved_by"],
                    line["note"],
                ),
            )

        # Store the full extraction JSON for audit/review
        extraction_json = {
            "lines": [
                {
                    "spoken": ln.spoken,
                    "kind": ln.kind,
                    "quantity": float(ln.quantity) if ln.quantity is not None else None,
                    "quantity_vague": ln.quantity_vague,
                    "unit": ln.unit,
                    "refers_to_previous": ln.refers_to_previous,
                }
                for ln in extraction.lines
            ],
            "customer_name": extraction.customer_name,
            "site_address": extraction.site_address,
        }

        cursor.execute(
            """
            UPDATE memo
            SET extraction_json = ?, status = 'completed'
            WHERE id = ?
            """,
            (json.dumps(extraction_json), memo_id),
        )
        log_audit_event(
            conn,
            business_id=business_id,
            entity="memo",
            entity_id=memo_id,
            event="quote_persisted",
            payload={
                "quote_id": quote_id,
                "version_id": version_id,
                "line_count": len(quote_lines),
            },
            actor="system",
        )
        conn.commit()

    return {"quote_id": quote_id, "version_id": version_id, "total_cents": total_cents}


class JobWorker:
    def __init__(self, poll_interval_sec: float = 1.0):
        self.poll_interval = poll_interval_sec
        self.running = False

    async def start(self, handler: Callable[[str], Coroutine]):
        """Runs the worker loop, polling for queued jobs."""
        self.running = True
        logger.info("JobWorker started polling SQLite queue.")
        while self.running:
            try:
                job_id = self._claim_next_job()
                if job_id:
                    logger.info("Processing job %s", job_id)
                    try:
                        await handler(job_id)
                        self._complete_job(job_id)
                    except Exception as exc:
                        logger.exception("Job %s failed", job_id)
                        self._fail_job(job_id, str(exc))
                else:
                    await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error("Error in job worker loop: %s", e)
                await asyncio.sleep(self.poll_interval)

    def stop(self):
        self.running = False

    def _claim_next_job(self) -> str | None:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id FROM job
                   WHERE state = 'queued'
                   ORDER BY updated_at ASC LIMIT 1"""
            )
            row = cursor.fetchone()
            if row:
                job_id = row["id"]
                cursor.execute(
                    """UPDATE job SET state = 'processing', attempts = attempts + 1,
                       updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                    (job_id,),
                )
                return job_id
        return None

    def _complete_job(self, job_id: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE job SET state = 'completed',
                   updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (job_id,),
            )

    def _fail_job(self, job_id: str, error_msg: str):
        audio_hash = None
        memo_id = None
        with get_db() as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                """SELECT m.id, m.audio_hash FROM job j
                   JOIN memo m ON m.id = j.memo_id WHERE j.id = ?""",
                (job_id,),
            ).fetchone()
            if row:
                memo_id = row["id"]
                audio_hash = row["audio_hash"]
            cursor.execute(
                """UPDATE job SET state = 'failed', error = ?,
                   updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (error_msg, job_id),
            )
            cursor.execute(
                """UPDATE memo SET status = 'failed'
                   WHERE id = (SELECT memo_id FROM job WHERE id = ?)""",
                (job_id,),
            )
        if memo_id and audio_hash:
            _apply_audio_retention(memo_id, audio_hash)


async def process_job(job_id: str) -> dict:
    """Process a queued job: transcribe audio, extract via LLM, persist quote draft."""
    # Get memo info including audio path
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT m.id, m.quote_id, m.transcript, m.kind, m.audio_hash, j.state
            FROM job j
            JOIN memo m ON m.id = j.memo_id
            WHERE j.id = ?
            """,
            (job_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Job {job_id} not found")

    memo_id = row["id"]
    transcript = row["transcript"]
    audio_hash = row["audio_hash"]

    # If no transcript but audio exists, transcribe it
    if not transcript and audio_hash:
        audio_path = Path(settings.audio_storage_dir) / audio_hash
        if not audio_path.is_file():
            raise FileNotFoundError(f"Uploaded audio is missing for memo {memo_id}")
        logger.info("Transcribing audio for memo %s", memo_id)
        transcriber = Transcriber()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)
        try:
            normalize_audio_to_wav(audio_path, wav_path)
            transcript = transcriber.transcribe(wav_path).strip()
        finally:
            wav_path.unlink(missing_ok=True)
        if not transcript:
            raise ValueError(f"Transcription returned no speech for memo {memo_id}")
        logger.info("Transcription complete for memo %s", memo_id)
        with get_db() as conn:
            conn.execute("UPDATE memo SET transcript = ? WHERE id = ?", (transcript, memo_id))
    elif not transcript:
        raise ValueError(f"Memo {memo_id} has neither a transcript nor audio")

    # Extract structured data via LLM
    extraction = await extract_with_llm(transcript)

    # Persist quote from extraction
    result = persist_quote_from_extraction(memo_id, extraction, business_id="biz_default")
    _apply_audio_retention(memo_id, audio_hash)
    return result


def _apply_audio_retention(memo_id: str, audio_hash: str | None) -> None:
    """Delete raw audio immediately by default, or expire old retained audio."""
    if not audio_hash:
        return
    audio_dir = Path(settings.audio_storage_dir)
    with get_db() as conn:
        if settings.audio_retention_days <= 0:
            conn.execute(
                "UPDATE memo SET audio_deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
                (memo_id,),
            )
            hashes_to_check = [audio_hash]
        else:
            retention = f"-{settings.audio_retention_days} days"
            hashes_to_check = [
                row["audio_hash"]
                for row in conn.execute(
                    """SELECT DISTINCT audio_hash FROM memo
                       WHERE audio_hash IS NOT NULL AND audio_deleted_at IS NULL
                         AND created_at <= datetime('now', ?)""",
                    (retention,),
                ).fetchall()
            ]
            for expired_hash in hashes_to_check:
                conn.execute(
                    """UPDATE memo SET audio_deleted_at = CURRENT_TIMESTAMP
                       WHERE audio_hash = ? AND audio_deleted_at IS NULL
                         AND created_at <= datetime('now', ?)""",
                    (expired_hash, retention),
                )

        for expired_hash in hashes_to_check:
            pending_reference = conn.execute(
                """SELECT 1 FROM memo
                   WHERE audio_hash = ? AND audio_deleted_at IS NULL LIMIT 1""",
                (expired_hash,),
            ).fetchone()
            if not pending_reference:
                (audio_dir / expired_hash).unlink(missing_ok=True)
