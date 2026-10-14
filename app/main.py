"""FastAPI entrypoint for TalkQuote (PLAN.md §10)."""

import asyncio
import hashlib
import json
import re
import uuid
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.audit import log_audit_event
from app.auth import require_auth, verify_pin
from app.config import APP_NAME, settings
from app.db import fetch_alias_map, get_db, init_db
from app.jobs import JobWorker, process_job
from app.match import PriceItemCandidate, match_line
from app.pdf import PDFGenerator
from app.pricing import (
    calculate_line_total_cents,
    calculate_quote_totals,
    format_cents_to_display,
)
from app.tracing import local_stage

security = HTTPBearer(auto_error=False)
WEB_BUILD_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    Path(settings.audio_storage_dir).mkdir(parents=True, exist_ok=True)
    worker = JobWorker()
    worker_task = asyncio.create_task(worker.start(process_job), name="talkquote-job-worker")
    app.state.job_worker = worker
    app.state.job_worker_task = worker_task
    try:
        yield
    finally:
        worker.stop()
        await worker_task


app = FastAPI(
    title=APP_NAME,
    description="Voice-to-Quote for plumbers. Model extracts, code prices, human approves.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    pin: str


class LoginResponse(BaseModel):
    token: str


class QuoteApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approver_name: str = Field(min_length=1, max_length=120)

    @field_validator("approver_name")
    @classmethod
    def normalize_approver_name(cls, value: str) -> str:
        name = " ".join(value.split())
        if not name:
            raise ValueError("Approver name cannot be blank")
        return name


class SystemStatusResponse(BaseModel):
    app_name: str
    version: str
    offline_mode: bool
    currency: str
    vat_rate_bp: int
    models: dict[str, str]


class LineUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_item_id: int | None = Field(default=None, gt=0)
    quantity_milli: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)
    alias_phrase: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("alias_phrase")
    @classmethod
    def normalize_alias_phrase(cls, value: str | None) -> str | None:
        if value is None:
            return None
        phrase = " ".join(value.split()).casefold()
        if not phrase or re.search(r"[$£€¥₹]|\bR\s*\d", phrase, re.IGNORECASE):
            raise ValueError("Alias must be item wording without a currency amount")
        return phrase


class VariationLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spoken: str = Field(min_length=1, max_length=300)
    kind: Literal["part", "labour", "callout", "other"]
    price_item_id: int = Field(gt=0)
    quantity_milli: int = Field(gt=0)

    @field_validator("spoken")
    @classmethod
    def reject_currency_in_spoken(cls, value: str) -> str:
        if re.search(r"[$£€¥₹]|\bR\s*\d", value, re.IGNORECASE):
            raise ValueError("Spoken wording must not contain currency amounts")
        return value.strip()


class VariationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memo_id: str
    based_on_version: int = Field(ge=1)
    lines: list[VariationLineInput] = Field(min_length=1)


class AliasCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phrase: str = Field(min_length=1, max_length=80)
    price_item_id: int = Field(gt=0)

    @field_validator("phrase")
    @classmethod
    def normalize_phrase(cls, value: str) -> str:
        phrase = " ".join(value.split()).casefold()
        if not phrase or re.search(r"[$£€¥₹]|\bR\s*\d", phrase, re.IGNORECASE):
            raise ValueError("Alias must be item wording without a currency amount")
        return phrase


class VariationApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approver_name: str = Field(min_length=1, max_length=120)

    @field_validator("approver_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        name = " ".join(value.split())
        if not name:
            raise ValueError("Approver name cannot be blank")
        return name


def _version_totals(conn, version_id: str, business_id: str) -> dict[str, int]:
    with local_stage("pricing_quote_totals"):
        cursor = conn.cursor()
        cursor.execute(
            "SELECT quantity_milli, unit_price_cents FROM quote_line "
            "WHERE version_id = ? AND variation_id IS NULL",
            (version_id,),
        )
        line_totals = [
            calculate_line_total_cents(row["quantity_milli"], row["unit_price_cents"])
            for row in cursor.fetchall()
        ]
        cursor.execute("SELECT vat_rate_bp FROM business WHERE id = ?", (business_id,))
        business = cursor.fetchone()
        if business is None:
            raise HTTPException(status_code=404, detail="Business not found")
        subtotal, vat, total = calculate_quote_totals(line_totals, business["vat_rate_bp"])
        cursor.execute(
            "UPDATE quote_version SET subtotal_cents = ?, vat_cents = ?, total_cents = ? "
            "WHERE id = ?",
            (subtotal, vat, total, version_id),
        )
        return {"subtotal_cents": subtotal, "vat_cents": vat, "total_cents": total}


def _clone_quote_version(conn, quote_id: str, source_version_id: str) -> tuple[str, dict[str, str]]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM quote_version WHERE id = ? AND quote_id = ?",
        (source_version_id, quote_id),
    )
    source = cursor.fetchone()
    if source is None:
        raise HTTPException(status_code=409, detail="Quote line is not in the current version")
    cursor.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM quote_version WHERE quote_id = ?",
        (quote_id,),
    )
    next_version = cursor.fetchone()[0]
    new_version_id = f"qv_{uuid.uuid4().hex[:12]}"
    cursor.execute(
        """INSERT INTO quote_version
           (id, quote_id, version, subtotal_cents, vat_cents, total_cents)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            new_version_id,
            quote_id,
            next_version,
            source["subtotal_cents"],
            source["vat_cents"],
            source["total_cents"],
        ),
    )
    cursor.execute(
        "SELECT * FROM quote_line WHERE version_id = ? AND variation_id IS NULL",
        (source_version_id,),
    )
    id_map: dict[str, str] = {}
    for row in cursor.fetchall():
        cloned_id = f"line_{uuid.uuid4().hex[:12]}"
        id_map[row["id"]] = cloned_id
        cursor.execute(
            """INSERT INTO quote_line
               (id, version_id, kind, spoken, price_item_id, quantity_milli, unit,
                unit_price_cents, match_outcome, match_score, resolved_by, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cloned_id,
                new_version_id,
                row["kind"],
                row["spoken"],
                row["price_item_id"],
                row["quantity_milli"],
                row["unit"],
                row["unit_price_cents"],
                row["match_outcome"],
                row["match_score"],
                row["resolved_by"],
                row["note"],
            ),
        )
    cursor.execute(
            "UPDATE quote SET status = CASE WHEN status = 'sent' THEN 'draft' "
            "ELSE status END WHERE id = ?",
            (quote_id,),
    )
    return new_version_id, id_map


def _save_learned_alias(conn, business_id: str, phrase: str, price_item_id: int) -> int:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name FROM price_item WHERE id = ? AND business_id = ? AND active = 1",
        (price_item_id, business_id),
    )
    item = cursor.fetchone()
    if item is None:
        raise HTTPException(
            status_code=422,
            detail="Selected item is not in this business price list",
        )
    cursor.execute(
        "SELECT id, price_item_id FROM alias WHERE business_id = ? AND lower(phrase) = lower(?)",
        (business_id, phrase),
    )
    current_alias = cursor.fetchone()
    if current_alias and current_alias["price_item_id"] != price_item_id:
        raise HTTPException(
            status_code=409,
            detail="This alias already points to a different price-list item",
        )
    if current_alias is None:
        cursor.execute(
            """INSERT INTO alias (business_id, phrase, price_item_id, source)
               VALUES (?, ?, ?, 'learned')""",
            (business_id, phrase, price_item_id),
        )
        return cursor.lastrowid
    return current_alias["id"]


def _validate_item_kind(kind: str, category: str, unit: str) -> None:
    if kind == "labour" and (category != "labour" or unit != "hours"):
        raise HTTPException(status_code=422, detail="Labour lines require a labour price-list item")
    if kind == "callout" and category != "callout":
        raise HTTPException(
            status_code=422,
            detail="Callout lines require a callout price-list item",
        )
    if kind == "part" and (category in ("labour", "callout") or unit == "hours"):
        raise HTTPException(status_code=422, detail="Part lines cannot use labour or callout items")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/system", response_model=SystemStatusResponse)
def get_system():
    return {
        "app_name": APP_NAME,
        "version": "0.1.0",
        "offline_mode": True,
        "currency": settings.default_currency,
        "vat_rate_bp": settings.default_vat_rate_bp,
        "models": {"asr": settings.whisper_model_size, "llm": settings.ollama_model},
    }


@app.post("/api/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    return {"token": verify_pin(req.pin)}


@app.post("/api/memos")
async def upload_memo(
    file: UploadFile = File(...),  # noqa: B008
    kind: str = Form("quote"),
    quote_id: str | None = Form(None),
    _token: str = Depends(require_auth),
):
    init_db()
    memo_id = f"memo_{uuid.uuid4().hex[:12]}"
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    transcript = ""
    audio_hash = None
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=422, detail="Memo upload is empty")
    content_type = file.content_type or ""
    if content_type.startswith("audio/") or (file.filename or "").endswith(
        (".wav", ".mp3", ".m4a", ".ogg", ".webm", ".mp4")
    ):
        audio_hash = hashlib.sha256(file_bytes).hexdigest()[:32]
        audio_path = Path(settings.audio_storage_dir) / audio_hash
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(file_bytes)
    elif content_type.startswith("text/") or (file.filename or "").endswith(".txt"):
        transcript = file_bytes.decode("utf-8", errors="strict").strip()
        if not transcript:
            raise HTTPException(status_code=422, detail="Transcript is empty")
    else:
        raise HTTPException(
            status_code=415,
            detail="Upload a supported audio file or text transcript",
        )

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO memo (id, business_id, quote_id, kind, status, transcript, audio_hash)
               VALUES (?, ?, ?, ?, 'queued', ?, ?)""",
            (memo_id, settings.default_business_id, quote_id, kind, transcript, audio_hash),
        )
        cursor.execute(
            "INSERT INTO job (id, memo_id, state) VALUES (?, ?, 'queued')",
            (job_id, memo_id),
        )
        log_audit_event(
            conn,
            settings.default_business_id,
            "memo",
            memo_id,
            "uploaded",
            {
                "filename": file.filename,
                "kind": kind,
                "job_id": job_id,
                "audio_hash": audio_hash,
            },
        )
    return {"memo_id": memo_id, "job_id": job_id, "status": "queued", "transcript": transcript}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str, _token: str = Depends(require_auth)):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, memo_id, state, attempts, error FROM job WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return dict(row)


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, _token: str = Depends(require_auth)):
    """Stream job state changes to the local PWA."""

    async def event_generator():
        last_state = None
        while True:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT state, error FROM job WHERE id = ?", (job_id,)
                ).fetchone()
            if row is None:
                yield 'data: {"error": "Job not found"}\n\n'
                break
            if row["state"] != last_state:
                yield f'data: {json.dumps({"state": row["state"]})}\n\n'
                last_state = row["state"]
            if row["state"] in ("completed", "failed"):
                if row["state"] == "failed":
                    yield f'data: {json.dumps({"error": row["error"]})}\n\n'
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/api/memos/{memo_id}")
def get_memo(memo_id: str, _token: str = Depends(require_auth)):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM memo WHERE id = ?", (memo_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Memo not found")
        return dict(row)


@app.get("/api/quotes/{quote_id}")
def get_quote(quote_id: str, _token: str = Depends(require_auth)):
    with get_db() as conn:
        quote = conn.execute("SELECT * FROM quote WHERE id = ?", (quote_id,)).fetchone()
        if quote is None:
            raise HTTPException(status_code=404, detail="Quote not found")
        version = conn.execute(
            "SELECT * FROM quote_version WHERE quote_id = ? ORDER BY version DESC LIMIT 1",
            (quote_id,),
        ).fetchone()
        lines: list[dict[str, Any]] = []
        if version is not None:
            for row in conn.execute(
                "SELECT * FROM quote_line WHERE version_id = ? AND variation_id IS NULL",
                (version["id"],),
            ).fetchall():
                line = dict(row)
                line["line_total_cents"] = calculate_line_total_cents(
                    line["quantity_milli"], line["unit_price_cents"]
                )
                lines.append(line)
        return {
            "quote": dict(quote),
            "version": dict(version) if version else None,
            "lines": lines,
            "currency": conn.execute(
                "SELECT currency FROM business WHERE id = ?", (quote["business_id"],)
            ).fetchone()["currency"],
            "vat_rate_bp": conn.execute(
                "SELECT vat_rate_bp FROM business WHERE id = ?", (quote["business_id"],)
            ).fetchone()["vat_rate_bp"],
        }


@app.patch("/api/quotes/{quote_id}/lines/{line_id}")
def update_quote_line(
    quote_id: str,
    line_id: str,
    update: LineUpdateRequest,
    _token: str = Depends(require_auth),
):
    changes = update.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="At least one correction is required")
    with local_stage("review_line_resolution"):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM quote WHERE id = ?", (quote_id,))
            quote = cursor.fetchone()
            if quote is None:
                raise HTTPException(status_code=404, detail="Quote not found")

            cursor.execute(
                """SELECT ql.*, qv.sent_at, qv.version
                   FROM quote_line ql JOIN quote_version qv ON qv.id = ql.version_id
                   WHERE ql.id = ? AND qv.quote_id = ?""",
                (line_id, quote_id),
            )
            line = cursor.fetchone()
            if line is None:
                raise HTTPException(status_code=404, detail="Quote line not found")

            cursor.execute(
                "SELECT id FROM quote_version WHERE quote_id = ? ORDER BY version DESC LIMIT 1",
                (quote_id,),
            )
            latest_version = cursor.fetchone()
            if line["version_id"] != latest_version["id"]:
                raise HTTPException(
                    status_code=409,
                    detail="This line is from an older quote version",
                )

            is_sent = quote["status"] in ("sent", "accepted") or line["sent_at"] is not None
            target_version_id = line["version_id"]
            target_line_id = line_id
            version_number = line["version"]
            if is_sent:
                target_version_id, id_map = _clone_quote_version(conn, quote_id, line["version_id"])
                target_line_id = id_map[line_id]
                version_number += 1
                cursor.execute(
                    "SELECT * FROM quote_line WHERE id = ?",
                    (target_line_id,),
                )
                line = cursor.fetchone()

            new_price_item_id = update.price_item_id or line["price_item_id"]
            item = None
            if new_price_item_id is not None:
                item = cursor.execute(
                    """SELECT id, name, unit, price_cents, category FROM price_item
                       WHERE id = ? AND business_id = ? AND active = 1""",
                    (new_price_item_id, quote["business_id"]),
                ).fetchone()
                if item is None:
                    raise HTTPException(status_code=422, detail="Selected item is not available")
                _validate_item_kind(line["kind"], item["category"], item["unit"])

            if update.alias_phrase is not None and update.price_item_id is None:
                raise HTTPException(
                    status_code=422,
                    detail="Select the corrected price-list item before saving an alias",
                )
            if update.alias_phrase is not None:
                _save_learned_alias(
                    conn, quote["business_id"], update.alias_phrase, new_price_item_id
                )

            quantity_milli = (
                update.quantity_milli
                if update.quantity_milli is not None
                else line["quantity_milli"]
            )
            unit_price_cents = (
                item["price_cents"] if update.price_item_id else line["unit_price_cents"]
            )
            item_id = item["id"] if update.price_item_id else line["price_item_id"]
            unit = item["unit"] if update.price_item_id else line["unit"]
            outcome = "confident" if update.price_item_id else line["match_outcome"]
            score = 100.0 if update.price_item_id else line["match_score"]
            resolved_by = (
                "user"
                if update.price_item_id or update.quantity_milli is not None
                else line["resolved_by"]
            )
            note = (
                update.note
                if update.note is not None
                else None
                if update.price_item_id
                else line["note"]
            )
            cursor.execute(
                """UPDATE quote_line SET price_item_id = ?, quantity_milli = ?, unit = ?,
                   unit_price_cents = ?, match_outcome = ?, match_score = ?,
                   resolved_by = ?, note = ?
                   WHERE id = ? AND version_id = ?""",
                (
                    item_id,
                    quantity_milli,
                    unit,
                    unit_price_cents,
                    outcome,
                    score,
                    resolved_by,
                    note,
                    target_line_id,
                    target_version_id,
                ),
            )
            totals = _version_totals(conn, target_version_id, quote["business_id"])
            if quote["status"] == "accepted":
                cursor.execute("UPDATE quote SET status = 'draft' WHERE id = ?", (quote_id,))
            log_audit_event(
                conn,
                quote["business_id"],
                "quote_line",
                target_line_id,
                "user_override",
                {
                    "quote_id": quote_id,
                    "source_line_id": line_id,
                    "version": version_number,
                    **changes,
                },
                actor="plumber",
            )
            if update.alias_phrase:
                log_audit_event(
                    conn,
                    quote["business_id"],
                    "quote_line",
                    target_line_id,
                    "learned_alias",
                    {"phrase": update.alias_phrase, "price_item_id": item_id},
                    actor="plumber",
                )
            return {
                "status": "updated",
                "line_id": target_line_id,
                "version_id": target_version_id,
                "version": version_number,
                **totals,
            }


@app.get("/api/quotes/{quote_id}/lines")
def get_quote_lines(quote_id: str, _token: str = Depends(require_auth)):
    with get_db() as conn:
        quote = conn.execute("SELECT id FROM quote WHERE id = ?", (quote_id,)).fetchone()
        if quote is None:
            raise HTTPException(status_code=404, detail="Quote not found")
        version = conn.execute(
            "SELECT id FROM quote_version WHERE quote_id = ? ORDER BY version DESC LIMIT 1",
            (quote_id,),
        ).fetchone()
        if version is None:
            return {"quote_id": quote_id, "lines": []}
        lines = []
        for row in conn.execute(
            "SELECT * FROM quote_line WHERE version_id = ? ORDER BY rowid",
            (version["id"],),
        ).fetchall():
            line = dict(row)
            line["line_total_cents"] = calculate_line_total_cents(
                line["quantity_milli"], line["unit_price_cents"]
            )
            lines.append(line)
        return {"quote_id": quote_id, "lines": lines}


@app.post("/api/quotes/{quote_id}/approve")
def approve_quote(
    quote_id: str,
    request: QuoteApprovalRequest,
    _token: str = Depends(require_auth),
):
    with get_db() as conn:
        quote = conn.execute("SELECT * FROM quote WHERE id = ?", (quote_id,)).fetchone()
        if quote is None:
            raise HTTPException(status_code=404, detail="Quote not found")
        if quote["status"] != "draft":
            raise HTTPException(status_code=409, detail="Only a draft quote can be approved")
        version = conn.execute(
            "SELECT id FROM quote_version WHERE quote_id = ? ORDER BY version DESC LIMIT 1",
            (quote_id,),
        ).fetchone()
        if version is None:
            raise HTTPException(status_code=409, detail="Quote has no version to approve")
        unresolved = conn.execute(
            "SELECT COUNT(*) FROM quote_line WHERE version_id = ? AND match_outcome != 'confident'",
            (version["id"],),
        ).fetchone()[0]
        if unresolved:
            raise HTTPException(status_code=409, detail="Resolve all flagged lines before approval")
        conn.execute("UPDATE quote SET status = 'accepted' WHERE id = ?", (quote_id,))
        log_audit_event(
            conn,
            quote["business_id"],
            "quote",
            quote_id,
            "approved",
            {"approver_name": request.approver_name},
            actor="plumber",
        )
        return {
            "status": "accepted",
            "quote_id": quote_id,
            "approver_name": request.approver_name,
        }


@app.post("/api/quotes/{quote_id}/send")
def send_quote(quote_id: str, _token: str = Depends(require_auth)):
    with get_db() as conn:
        quote = conn.execute(
            "SELECT business_id, status FROM quote WHERE id = ?", (quote_id,)
        ).fetchone()
        if quote is None:
            raise HTTPException(status_code=404, detail="Quote not found")
        if quote["status"] != "accepted":
            raise HTTPException(status_code=409, detail="Approve the quote before sending it")
        version = conn.execute(
            """SELECT id, version, total_cents FROM quote_version
               WHERE quote_id = ? ORDER BY version DESC LIMIT 1""",
            (quote_id,),
        ).fetchone()
        if version is None:
            raise HTTPException(status_code=409, detail="Quote has no version to send")
        unresolved = conn.execute(
            "SELECT COUNT(*) FROM quote_line WHERE version_id = ? AND match_outcome != 'confident'",
            (version["id"],),
        ).fetchone()[0]
        if unresolved:
            raise HTTPException(status_code=409, detail="Resolve all flagged lines before sending")
        conn.execute(
            "UPDATE quote_version SET sent_at = CURRENT_TIMESTAMP WHERE id = ?",
            (version["id"],),
        )
        conn.execute("UPDATE quote SET status = 'sent' WHERE id = ?", (quote_id,))
        log_audit_event(
            conn,
            quote["business_id"],
            "quote",
            quote_id,
            "sent",
            {"version": version["version"], "total_cents": version["total_cents"]},
            actor="plumber",
        )
        return {
            "status": "sent",
            "quote_id": quote_id,
            "total_cents": version["total_cents"],
        }


@app.get("/api/quotes/{quote_id}/lines/{line_id}/candidates")
def get_line_candidates(
    quote_id: str,
    line_id: str,
    _token: str = Depends(require_auth),
):
    with get_db() as conn:
        line = conn.execute(
            """SELECT ql.spoken, q.business_id FROM quote_line ql
               JOIN quote_version qv ON qv.id = ql.version_id
               JOIN quote q ON q.id = qv.quote_id
               WHERE ql.id = ? AND qv.quote_id = ?""",
            (line_id, quote_id),
        ).fetchone()
        if line is None:
            raise HTTPException(status_code=404, detail="Quote line not found")
        rows = conn.execute(
            """SELECT id, sku, name, unit, price_cents, category, attrs_json
               FROM price_item WHERE business_id = ? AND active = 1""",
            (line["business_id"],),
        ).fetchall()
        items = [
            PriceItemCandidate(
                id=row["id"],
                sku=row["sku"],
                name=row["name"],
                unit=row["unit"],
                price_cents=row["price_cents"],
                category=row["category"],
                attrs=json.loads(row["attrs_json"] or "{}"),
            )
            for row in rows
        ]
        direct_alias = conn.execute(
            """SELECT pi.id, pi.sku, pi.name, pi.unit, pi.price_cents, pi.category
               FROM alias a JOIN price_item pi ON pi.id = a.price_item_id
               WHERE a.business_id = ? AND lower(a.phrase) = lower(?)
                 AND pi.active = 1""",
            (line["business_id"], line["spoken"]),
        ).fetchone()
        if direct_alias is not None:
            candidates = [
                {
                    "price_item_id": direct_alias["id"],
                    "sku": direct_alias["sku"],
                    "name": direct_alias["name"],
                    "unit": direct_alias["unit"],
                    "price_cents": direct_alias["price_cents"],
                    "score": 100.0,
                }
            ]
            return {
                "outcome": "confident",
                "flag_reason": None,
                "candidates": candidates,
            }

        result = match_line(
            line["spoken"],
            items,
            alias_map=fetch_alias_map(conn, business_id=line["business_id"]),
        )
        return {
            "outcome": result.outcome.value,
            "flag_reason": result.flag_reason,
            "candidates": [
                {
                    "price_item_id": candidate.item.id,
                    "sku": candidate.item.sku,
                    "name": candidate.item.name,
                    "unit": candidate.item.unit,
                    "price_cents": candidate.item.price_cents,
                    "score": candidate.score,
                }
                for candidate in result.candidates
            ],
        }


@app.post("/api/quotes/{quote_id}/variations", status_code=201)
def create_variation(
    quote_id: str,
    request: VariationCreateRequest,
    _token: str = Depends(require_auth),
):
    with local_stage("variation_create"):
        with get_db() as conn:
            cursor = conn.cursor()
            quote = cursor.execute("SELECT * FROM quote WHERE id = ?", (quote_id,)).fetchone()
            if quote is None:
                raise HTTPException(status_code=404, detail="Quote not found")
            memo = cursor.execute(
                "SELECT id, business_id, quote_id, kind FROM memo WHERE id = ?",
                (request.memo_id,),
            ).fetchone()
            if (
                memo is None
                or memo["business_id"] != quote["business_id"]
                or memo["quote_id"] != quote_id
                or memo["kind"] != "variation"
            ):
                raise HTTPException(
                    status_code=422,
                    detail="Variation memo must belong to this quote and be marked as a variation",
                )
            base_version = cursor.execute(
                """SELECT id, version FROM quote_version
                   WHERE quote_id = ? AND version = ? AND sent_at IS NOT NULL""",
                (quote_id, request.based_on_version),
            ).fetchone()
            if base_version is None:
                raise HTTPException(
                    status_code=409,
                    detail="Variation must link to a sent version of this quote",
                )

            normalized_lines = []
            line_totals = []
            for line in request.lines:
                item = cursor.execute(
                    """SELECT id, unit, price_cents, category FROM price_item
                       WHERE id = ? AND business_id = ? AND active = 1""",
                    (line.price_item_id, quote["business_id"]),
                ).fetchone()
                if item is None:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Price-list item {line.price_item_id} is unavailable",
                    )
                _validate_item_kind(line.kind, item["category"], item["unit"])
                total = calculate_line_total_cents(line.quantity_milli, item["price_cents"])
                line_totals.append(total)
                normalized_lines.append((line, item, total))

            business = cursor.execute(
                "SELECT vat_rate_bp FROM business WHERE id = ?",
                (quote["business_id"],),
            ).fetchone()
            subtotal, vat, total = calculate_quote_totals(line_totals, business["vat_rate_bp"])
            cursor.execute("SELECT COUNT(*) FROM variation WHERE quote_id = ?", (quote_id,))
            sequence = cursor.fetchone()[0] + 1
            variation_id = f"var_{uuid.uuid4().hex[:12]}"
            variation_number = f"{quote['number']}-V{sequence}"
            cursor.execute(
                """INSERT INTO variation
                   (id, business_id, quote_id, memo_id, based_on_version, number, status,
                    subtotal_cents, vat_cents, total_cents)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
                (
                    variation_id,
                    quote["business_id"],
                    quote_id,
                    request.memo_id,
                    request.based_on_version,
                    variation_number,
                    subtotal,
                    vat,
                    total,
                ),
            )
            for line, item, _line_total in normalized_lines:
                cursor.execute(
                    """INSERT INTO variation_line
                       (id, business_id, variation_id, kind, spoken, price_item_id,
                        quantity_milli, unit, unit_price_cents, match_outcome, match_score)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'confident', 100)""",
                    (
                        f"vline_{uuid.uuid4().hex[:12]}",
                        quote["business_id"],
                        variation_id,
                        line.kind,
                        line.spoken,
                        item["id"],
                        line.quantity_milli,
                        item["unit"],
                        item["price_cents"],
                    ),
                )
            log_audit_event(
                conn,
                quote["business_id"],
                "variation",
                variation_id,
                "created",
                {
                    "quote_id": quote_id,
                    "memo_id": request.memo_id,
                    "based_on_version": request.based_on_version,
                    "line_count": len(normalized_lines),
                    "subtotal_cents": subtotal,
                    "vat_cents": vat,
                    "total_cents": total,
                },
                actor="plumber",
            )
            return {
                "variation_id": variation_id,
                "number": variation_number,
                "status": "pending",
                "based_on_version": request.based_on_version,
                "subtotal_cents": subtotal,
                "vat_cents": vat,
                "total_cents": total,
            }


@app.get("/api/variations/{variation_id}")
def get_variation(variation_id: str, _token: str = Depends(require_auth)):
    with get_db() as conn:
        variation = conn.execute(
            """SELECT v.*, q.number AS quote_number, q.customer_name, q.site_address,
                      b.currency
               FROM variation v JOIN quote q ON q.id = v.quote_id
               JOIN business b ON b.id = v.business_id WHERE v.id = ?""",
            (variation_id,),
        ).fetchone()
        if variation is None:
            raise HTTPException(status_code=404, detail="Variation not found")
        lines = [
            dict(row)
            for row in conn.execute(
                """SELECT vl.*, pi.name AS item_name FROM variation_line vl
                   LEFT JOIN price_item pi ON pi.id = vl.price_item_id
                   WHERE vl.variation_id = ? ORDER BY vl.rowid""",
                (variation_id,),
            ).fetchall()
        ]
        return {"variation": dict(variation), "lines": lines}


@app.post("/api/variations/{variation_id}/approve")
def approve_variation(
    variation_id: str,
    request: VariationApprovalRequest,
    _token: str = Depends(require_auth),
):
    with local_stage("variation_approval"):
        with get_db() as conn:
            cursor = conn.cursor()
            variation = cursor.execute(
                "SELECT business_id, status FROM variation WHERE id = ?",
                (variation_id,),
            ).fetchone()
            if variation is None:
                raise HTTPException(status_code=404, detail="Variation not found")
            if variation["status"] != "pending":
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot approve a variation with status {variation['status']}",
                )
            cursor.execute(
                """UPDATE variation SET status = 'approved', approved_by_name = ?,
                   approved_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (request.approver_name, variation_id),
            )
            log_audit_event(
                conn,
                variation["business_id"],
                "variation",
                variation_id,
                "approved",
                {"approver_name": request.approver_name},
                actor="plumber",
            )
            return {
                "status": "approved",
                "variation_id": variation_id,
                "approver_name": request.approver_name,
            }


@app.get("/api/variations/{variation_id}/pdf")
def variation_pdf(variation_id: str, _token: str = Depends(require_auth)):
    with get_db() as conn:
        variation = conn.execute(
            """SELECT v.*, q.number AS quote_number, q.customer_name, q.site_address,
                      b.currency
               FROM variation v JOIN quote q ON q.id = v.quote_id
               JOIN business b ON b.id = v.business_id WHERE v.id = ?""",
            (variation_id,),
        ).fetchone()
        if variation is None:
            raise HTTPException(status_code=404, detail="Variation not found")
        lines = conn.execute(
            """SELECT vl.*, pi.name AS item_name FROM variation_line vl
               LEFT JOIN price_item pi ON pi.id = vl.price_item_id
               WHERE vl.variation_id = ? ORDER BY vl.rowid""",
            (variation_id,),
        ).fetchall()
        line_data = []
        for line in lines:
            line_data.append(
                {
                    "name": line["item_name"] or line["spoken"],
                    "quantity_display": f"{Decimal(line['quantity_milli']) / Decimal(1000):f}",
                    "unit": line["unit"] or "",
                    "unit_price_display": format_cents_to_display(
                        line["unit_price_cents"], variation["currency"]
                    ),
                    "line_total_display": format_cents_to_display(
                        calculate_line_total_cents(
                            line["quantity_milli"], line["unit_price_cents"]
                        ),
                        variation["currency"],
                    ),
                }
            )
        data = {
            "variation_number": variation["number"],
            "quote_number": variation["quote_number"],
            "based_on_version": variation["based_on_version"],
            "date": date.today().isoformat(),
            "customer_name": variation["customer_name"] or "",
            "site_address": variation["site_address"] or "",
            "lines": line_data,
            "subtotal_display": format_cents_to_display(
                variation["subtotal_cents"], variation["currency"]
            ),
            "vat_display": format_cents_to_display(variation["vat_cents"], variation["currency"]),
            "total_display": format_cents_to_display(
                variation["total_cents"], variation["currency"]
            ),
            "approved_by_name": variation["approved_by_name"],
            "approved_at": variation["approved_at"],
            "audit_id": variation_id,
        }
    with local_stage("variation_pdf"):
        try:
            from weasyprint import HTML

            html = PDFGenerator().render_variation_html(data)
            pdf_bytes = HTML(string=html).write_pdf()
        except Exception as exc:  # weasyprint raises various conversion errors when Pango is absent
            raise HTTPException(
                status_code=503,
                detail=(
                    "PDF rendering failed; check that WeasyPrint Pango dependencies "
                    "are installed"
                ),
            ) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{variation_id}.pdf"'},
    )


@app.post("/api/aliases", status_code=201)
def create_alias(
    request: AliasCreateRequest,
    _token: str = Depends(require_auth),
):
    with get_db() as conn:
        alias_id = _save_learned_alias(
            conn,
            settings.default_business_id,
            request.phrase,
            request.price_item_id,
        )
        log_audit_event(
            conn,
            settings.default_business_id,
            "alias",
            str(alias_id),
            "saved",
            {
                "phrase": request.phrase,
                "price_item_id": request.price_item_id,
            },
            actor="plumber",
        )
        return {"id": alias_id, "phrase": request.phrase, "price_item_id": request.price_item_id}


@app.delete("/api/aliases/{alias_id}")
def delete_alias(alias_id: int, _token: str = Depends(require_auth)):
    with get_db() as conn:
        alias = conn.execute(
            """SELECT phrase, source, business_id FROM alias
               WHERE id = ? AND business_id = ?""",
            (alias_id, settings.default_business_id),
        ).fetchone()
        if alias is None:
            raise HTTPException(status_code=404, detail="Alias not found")
        if alias["source"] != "learned":
            raise HTTPException(status_code=409, detail="Seed aliases cannot be removed")
        log_audit_event(
            conn,
            alias["business_id"],
            "alias",
            str(alias_id),
            "deleted",
            {"phrase": alias["phrase"]},
            actor="plumber",
        )
        conn.execute("DELETE FROM alias WHERE id = ?", (alias_id,))
        return {"status": "deleted", "id": alias_id}


@app.get("/api/aliases")
def get_aliases(_token: str = Depends(require_auth)):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT a.id, a.phrase, a.price_item_id, a.source, p.name AS canonical_name
               FROM alias a JOIN price_item p
                 ON p.id = a.price_item_id AND p.business_id = a.business_id
               WHERE a.business_id = ?
               ORDER BY a.phrase""",
            (settings.default_business_id,),
        ).fetchall()
        return [dict(row) for row in rows]


@app.get("/api/audit")
def get_audit_trail(quote_id: str, _token: str = Depends(require_auth)):
    with get_db() as conn:
        quote = conn.execute("SELECT business_id FROM quote WHERE id = ?", (quote_id,)).fetchone()
        if quote is None:
            raise HTTPException(status_code=404, detail="Quote not found")
        rows = conn.execute(
            """SELECT id, ts, business_id, entity, entity_id, event, payload_json, actor
               FROM audit_log
               WHERE business_id = ? AND (
                   (entity = 'quote' AND entity_id = ?)
                   OR (entity = 'quote_line' AND entity_id IN (
                       SELECT ql.id FROM quote_line ql
                       JOIN quote_version qv ON qv.id = ql.version_id
                       WHERE qv.quote_id = ?
                   ))
                   OR (entity = 'variation' AND entity_id IN (
                       SELECT id FROM variation WHERE quote_id = ?
                   ))
                   OR (entity = 'memo' AND entity_id IN (
                       SELECT id FROM memo WHERE quote_id = ?
                   ))
               )
               ORDER BY ts, id""",
            (quote["business_id"], quote_id, quote_id, quote_id, quote_id),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "timestamp": row["ts"],
                "business_id": row["business_id"],
                "entity": row["entity"],
                "entity_id": row["entity_id"],
                "event": row["event"],
                "payload": json.loads(row["payload_json"]),
                "actor": row["actor"],
            }
            for row in rows
        ]


@app.get("/", include_in_schema=False)
def serve_web_root():
    index_file = WEB_BUILD_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Web app build not found")
    return FileResponse(index_file)


@app.get("/{web_path:path}", include_in_schema=False)
def serve_web_app(web_path: str):
    if web_path == "api" or web_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    build_root = WEB_BUILD_DIR.resolve()
    requested_file = (WEB_BUILD_DIR / web_path).resolve()
    if requested_file.is_relative_to(build_root) and requested_file.is_file():
        return FileResponse(requested_file)
    if Path(web_path).suffix:
        raise HTTPException(status_code=404, detail="Web asset not found")

    index_file = WEB_BUILD_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Web app build not found")
    return FileResponse(index_file)
