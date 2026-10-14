"""FastAPI entrypoint for TalkQuote (PLAN.md §10)."""
import asyncio
import hashlib
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from app.audit import fetch_audit_trail, log_audit_event
from app.auth import require_auth, verify_pin
from app.config import APP_NAME, settings
from app.db import get_db, init_db
from app.jobs import JobWorker, process_job
from app.pricing import (
    calculate_line_total_cents,
    calculate_quote_totals,
)

security = HTTPBearer(auto_error=False)
WEB_BUILD_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Ensure audio storage directory exists
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
    quantity_milli: int | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=500)


class QuoteApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approver_name: str = Field(min_length=1, max_length=120)


def _recalculate_quote_version(conn, version_id: str, business_id: str) -> dict[str, int]:
    lines = conn.execute(
        """SELECT quantity_milli, unit_price_cents FROM quote_line
           WHERE version_id = ? AND variation_id IS NULL""",
        (version_id,),
    ).fetchall()
    subtotal, vat, total = calculate_quote_totals(
        [
            calculate_line_total_cents(row["quantity_milli"], row["unit_price_cents"])
            for row in lines
        ],
        conn.execute(
            "SELECT vat_rate_bp FROM business WHERE id = ?", (business_id,)
        ).fetchone()["vat_rate_bp"],
    )
    conn.execute(
        """UPDATE quote_version SET subtotal_cents = ?, vat_cents = ?, total_cents = ?
           WHERE id = ?""",
        (subtotal, vat, total, version_id),
    )
    return {"subtotal_cents": subtotal, "vat_cents": vat, "total_cents": total}


def _create_quote_revision(
    conn, quote_id: str, old_version_id: str
) -> tuple[str, dict[str, str], int]:
    old = conn.execute(
        "SELECT * FROM quote_version WHERE id = ? AND quote_id = ?",
        (old_version_id, quote_id),
    ).fetchone()
    if old is None:
        raise HTTPException(status_code=404, detail="Quote version not found")
    version_number = conn.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM quote_version WHERE quote_id = ?",
        (quote_id,),
    ).fetchone()[0]
    new_version_id = f"qv_{uuid.uuid4().hex[:12]}"
    conn.execute(
        """INSERT INTO quote_version
           (id, quote_id, version, subtotal_cents, vat_cents, total_cents)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            new_version_id,
            quote_id,
            version_number,
            old["subtotal_cents"],
            old["vat_cents"],
            old["total_cents"],
        ),
    )
    id_map: dict[str, str] = {}
    old_lines = conn.execute(
        "SELECT * FROM quote_line WHERE version_id = ? AND variation_id IS NULL",
        (old_version_id,),
    ).fetchall()
    for old_line in old_lines:
        new_line_id = f"line_{uuid.uuid4().hex[:12]}"
        id_map[old_line["id"]] = new_line_id
        conn.execute(
            """INSERT INTO quote_line
               (id, version_id, kind, spoken, price_item_id, quantity_milli, unit,
                unit_price_cents, match_outcome, match_score, resolved_by, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_line_id,
                new_version_id,
                old_line["kind"],
                old_line["spoken"],
                old_line["price_item_id"],
                old_line["quantity_milli"],
                old_line["unit"],
                old_line["unit_price_cents"],
                old_line["match_outcome"],
                old_line["match_score"],
                old_line["resolved_by"],
                old_line["note"],
            ),
        )
    conn.execute("UPDATE quote SET status = 'draft' WHERE id = ?", (quote_id,))
    return new_version_id, id_map, version_number


@app.get("/healthz")
def healthz():
    """Liveness check."""
    return {"status": "ok"}


@app.get("/api/system", response_model=SystemStatusResponse)
def get_system():
    """System status and active configuration."""
    return {
        "app_name": APP_NAME,
        "version": "0.1.0",
        "offline_mode": True,
        "currency": settings.default_currency,
        "vat_rate_bp": settings.default_vat_rate_bp,
        "models": {
            "asr": settings.whisper_model_size,
            "llm": settings.ollama_model,
        },
    }


@app.post("/api/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    token = verify_pin(req.pin)
    return {"token": token}


@app.post("/api/memos")
async def upload_memo(
    file: UploadFile = File(...),
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
    if content_type.startswith("audio/") or file.filename.endswith(
        (".wav", ".mp3", ".m4a", ".ogg", ".webm", ".mp4")
    ):
        audio_hash = hashlib.sha256(file_bytes).hexdigest()[:32]
        audio_path = Path(settings.audio_storage_dir) / audio_hash
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(file_bytes)
    elif content_type.startswith("text/"):
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
               VALUES (?, 'biz_default', ?, ?, 'queued', ?, ?)""",
            (memo_id, quote_id, kind, transcript, audio_hash),
        )
        cursor.execute(
            """INSERT INTO job (id, memo_id, state)
               VALUES (?, ?, 'queued')""",
            (job_id, memo_id),
        )
        log_audit_event(
            conn,
            business_id="biz_default",
            entity="memo",
            entity_id=memo_id,
            event="uploaded",
            payload={
                "filename": file.filename,
                "kind": kind,
                "job_id": job_id,
                "audio_hash": audio_hash,
            },
        )

    return {"memo_id": memo_id, "job_id": job_id, "status": "queued", "transcript": transcript}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str, _token: str = Depends(require_auth)):
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, memo_id, state, attempts, error FROM job WHERE id = ?", (job_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        return dict(row)


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, _token: str = Depends(require_auth)):
    """SSE endpoint for real-time job status updates."""
    init_db()

    async def event_generator():
        import asyncio
        last_state = None
        while True:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT state, error FROM job WHERE id = ?", (job_id,)
                )
                row = cursor.fetchone()
                if not row:
                    yield "data: {\"error\": \"Job not found\"}\n\n"
                    break

                if row["state"] != last_state:
                    yield f"data: {{\"state\": \"{row['state']}\"}}\n\n"
                    last_state = row["state"]

                if row["state"] in ("completed", "failed"):
                    if row["state"] == "failed":
                        yield f"data: {{\"error\": \"{row['error']}\"}}\n\n"
                    break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/api/memos/{memo_id}")
def get_memo(memo_id: str, _token: str = Depends(require_auth)):
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memo WHERE id = ?", (memo_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Memo not found")
        return dict(row)


@app.patch("/api/quotes/{quote_id}/lines/{line_id}")
def update_quote_line(
    quote_id: str,
    line_id: str,
    update: LineUpdateRequest,
    _token: str = Depends(require_auth),
):
    init_db()
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
        if not line:
            raise HTTPException(status_code=404, detail="Quote line not found")

        latest_version = cursor.execute(
            "SELECT id FROM quote_version WHERE quote_id = ? ORDER BY version DESC LIMIT 1",
            (quote_id,),
        ).fetchone()
        if line["version_id"] != latest_version["id"]:
            raise HTTPException(status_code=409, detail="Cannot edit a line from an older version")

        line_id_to_update = line_id
        version_id = line["version_id"]
        version_number = line["version"]
        is_sent = quote["status"] == "sent" or line["sent_at"] is not None
        if is_sent:
            version_id, id_map, version_number = _create_quote_revision(
                conn, quote_id, line["version_id"]
            )
            line_id_to_update = id_map[line_id]
            line = cursor.execute(
                "SELECT * FROM quote_line WHERE id = ?",
                (line_id_to_update,),
            ).fetchone()

        selected_item = None
        if update.price_item_id is not None:
            selected_item = cursor.execute(
                """SELECT id, unit, price_cents, category FROM price_item
                   WHERE id = ? AND business_id = ? AND active = 1""",
                (update.price_item_id, quote["business_id"]),
            ).fetchone()
            if selected_item is None:
                raise HTTPException(
                    status_code=422,
                    detail="Selected item is not in this price list",
                )
            if line["kind"] == "labour" and selected_item["category"] != "labour":
                raise HTTPException(status_code=422, detail="Select a labour price-list item")
            if line["kind"] == "callout" and selected_item["category"] != "callout":
                raise HTTPException(status_code=422, detail="Select a callout price-list item")
            if line["kind"] == "part" and selected_item["category"] in ("labour", "callout"):
                raise HTTPException(
                    status_code=422,
                    detail="Part lines cannot use labour/callout items",
                )

        quantity_milli = (
            update.quantity_milli
            if update.quantity_milli is not None
            else line["quantity_milli"]
        )
        price_item_id = selected_item["id"] if selected_item else line["price_item_id"]
        unit = selected_item["unit"] if selected_item else line["unit"]
        unit_price_cents = (
            selected_item["price_cents"] if selected_item else line["unit_price_cents"]
        )
        match_outcome = "confident" if selected_item else line["match_outcome"]
        match_score = 100.0 if selected_item else line["match_score"]
        resolved_by = (
            "user"
            if selected_item or update.quantity_milli is not None
            else line["resolved_by"]
        )
        note = update.note if update.note is not None else (None if selected_item else line["note"])
        cursor.execute(
            """UPDATE quote_line SET price_item_id = ?, quantity_milli = ?, unit = ?,
               unit_price_cents = ?, match_outcome = ?, match_score = ?, resolved_by = ?, note = ?
               WHERE id = ? AND version_id = ?""",
            (
                price_item_id,
                quantity_milli,
                unit,
                unit_price_cents,
                match_outcome,
                match_score,
                resolved_by,
                note,
                line_id_to_update,
                version_id,
            ),
        )
        totals = _recalculate_quote_version(conn, version_id, quote["business_id"])
        if quote["status"] == "accepted":
            cursor.execute("UPDATE quote SET status = 'draft' WHERE id = ?", (quote_id,))

        log_audit_event(
            conn,
            business_id=quote["business_id"],
            entity="quote_line",
            entity_id=line_id_to_update,
            event="user_override",
            payload={
                "quote_id": quote_id,
                "source_line_id": line_id,
                "version": version_number,
                **update.model_dump(exclude_unset=True),
            },
            actor="plumber",
        )
        return {
            "status": "updated",
            "line_id": line_id_to_update,
            "version": version_number,
            "version_id": version_id,
            **totals,
        }


@app.get("/api/quotes/{quote_id}")
def get_quote(quote_id: str, _token: str = Depends(require_auth)):
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM quote WHERE id = ?", (quote_id,))
        quote_row = cursor.fetchone()
        if not quote_row:
            raise HTTPException(status_code=404, detail="Quote not found")

        cursor.execute(
            "SELECT * FROM quote_version WHERE quote_id = ? ORDER BY version DESC LIMIT 1",
            (quote_id,),
        )
        version_row = cursor.fetchone()

        lines: list[dict[str, Any]] = []
        if version_row:
            cursor.execute(
                "SELECT * FROM quote_line WHERE version_id = ? ORDER BY rowid ASC",
                (version_row["id"],),
            )
            lines = []
            for row in cursor.fetchall():
                line = dict(row)
                line["line_total_cents"] = calculate_line_total_cents(
                    line["quantity_milli"], line["unit_price_cents"]
                )
                lines.append(line)
        business = cursor.execute(
            "SELECT currency, vat_rate_bp FROM business WHERE id = ?",
            (quote_row["business_id"],),
        ).fetchone()

        return {
            "quote": dict(quote_row),
            "version": dict(version_row) if version_row else None,
            "lines": lines,
            "currency": business["currency"],
            "vat_rate_bp": business["vat_rate_bp"],
        }


@app.get("/api/quotes/{quote_id}/lines")
def get_quote_lines(quote_id: str, _token: str = Depends(require_auth)):
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM quote WHERE id = ?", (quote_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Quote not found")
        cursor.execute(
            "SELECT * FROM quote_version WHERE quote_id = ? ORDER BY version DESC LIMIT 1",
            (quote_id,),
        )
        version_row = cursor.fetchone()
        if not version_row:
            return {"quote_id": quote_id, "lines": []}
        cursor.execute(
            "SELECT * FROM quote_line WHERE version_id = ? ORDER BY rowid ASC",
            (version_row["id"],),
        )
        lines = []
        for row in cursor.fetchall():
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
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM quote WHERE id = ?", (quote_id,))
        quote_row = cursor.fetchone()
        if not quote_row:
            raise HTTPException(status_code=404, detail="Quote not found")

        if quote_row["status"] != "draft":
            raise HTTPException(status_code=409, detail="Only a draft quote can be approved")
        latest = cursor.execute(
            "SELECT id FROM quote_version WHERE quote_id = ? ORDER BY version DESC LIMIT 1",
            (quote_id,),
        ).fetchone()
        if latest is None:
            raise HTTPException(status_code=409, detail="Quote has no version to approve")
        unresolved = cursor.execute(
            """SELECT COUNT(*) FROM quote_line
               WHERE version_id = ? AND match_outcome != 'confident'""",
            (latest["id"],),
        ).fetchone()[0]
        if unresolved:
            raise HTTPException(status_code=409, detail="Resolve all flagged lines before approval")
        cursor.execute("UPDATE quote SET status = 'accepted' WHERE id = ?", (quote_id,))
        log_audit_event(
            conn,
            business_id="biz_default",
            entity="quote",
            entity_id=quote_id,
            event="approved",
            payload={"approver_name": request.approver_name},
            actor="plumber",
        )
        return {"status": "accepted", "quote_id": quote_id, "approver_name": request.approver_name}


@app.get("/api/audit")
def get_audit_trail(quote_id: str, _token: str = Depends(require_auth)):
    init_db()
    with get_db() as conn:
        return fetch_audit_trail(conn, "quote", quote_id)


@app.post("/api/quotes/{quote_id}/send")
def send_quote(quote_id: str, _token: str = Depends(require_auth)):
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, version, subtotal_cents, vat_cents, total_cents
            FROM quote_version
            WHERE quote_id = ?
            ORDER BY version DESC LIMIT 1
            """,
            (quote_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Quote not found")
        quote = cursor.execute(
            "SELECT business_id, status FROM quote WHERE id = ?", (quote_id,)
        ).fetchone()
        if quote["status"] != "accepted":
            raise HTTPException(status_code=409, detail="Approve the quote before sending it")
        unresolved = cursor.execute(
            """SELECT COUNT(*) FROM quote_line
               WHERE version_id = ? AND match_outcome != 'confident'""",
            (row["id"],),
        ).fetchone()[0]
        if unresolved:
            raise HTTPException(status_code=409, detail="Resolve all flagged lines before sending")
        cursor.execute(
            "UPDATE quote_version SET sent_at = CURRENT_TIMESTAMP WHERE id = ?",
            (row["id"],),
        )
        cursor.execute("UPDATE quote SET status = 'sent' WHERE id = ?", (quote_id,))
        log_audit_event(
            conn,
            business_id=quote["business_id"],
            entity="quote",
            entity_id=quote_id,
            event="sent",
            payload={"version": row["version"], "total_cents": row["total_cents"]},
            actor="plumber",
        )
        return {"status": "sent", "quote_id": quote_id, "total_cents": row["total_cents"]}


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

    requested_file = (WEB_BUILD_DIR / web_path).resolve()
    if requested_file.is_relative_to(WEB_BUILD_DIR.resolve()) and requested_file.is_file():
        return FileResponse(requested_file)

    if Path(web_path).suffix:
        raise HTTPException(status_code=404, detail="Web asset not found")

    index_file = WEB_BUILD_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Web app build not found")
    return FileResponse(index_file)
