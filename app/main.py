"""FastAPI entrypoint for TalkQuote (PLAN.md §10)."""
from contextlib import asynccontextmanager
from typing import Any
import uuid
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings, APP_NAME
from app.db import init_db, get_db
from app.auth import verify_pin, require_auth
from app.extract import Extraction, get_extraction_schema
from app.pricing import calculate_line_total_cents, calculate_quote_totals, format_cents_to_display
from app.audit import log_audit_event, fetch_audit_trail

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

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
    price_item_id: int | None = None
    quantity_milli: int | None = None
    unit_price_cents: int | None = None
    note: str | None = None

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
):
    memo_id = f"memo_{uuid.uuid4().hex[:12]}"
    job_id = f"job_{uuid.uuid4().hex[:12]}"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO memo (id, business_id, quote_id, kind, status)
               VALUES (?, 'biz_default', ?, ?, 'queued')""",
            (memo_id, quote_id, kind),
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
            payload={"filename": file.filename, "kind": kind, "job_id": job_id},
        )

    return {"memo_id": memo_id, "job_id": job_id, "status": "queued"}

@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, memo_id, state, attempts, error FROM job WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        return dict(row)

@app.get("/api/memos/{memo_id}")
def get_memo(memo_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memo WHERE id = ?", (memo_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Memo not found")
        return dict(row)

@app.patch("/api/quotes/{quote_id}/lines/{line_id}")
def update_quote_line(quote_id: str, line_id: str, update: LineUpdateRequest):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM quote_line WHERE id = ?", (line_id,))
        line = cursor.fetchone()
        if not line:
            raise HTTPException(status_code=404, detail="Quote line not found")
        
        # Log audit entry for every manual edit (PLAN.md §3)
        log_audit_event(
            conn,
            business_id="biz_default",
            entity="quote_line",
            entity_id=line_id,
            event="user_override",
            payload=update.model_dump(exclude_unset=True),
            actor="plumber",
        )
        return {"status": "updated", "line_id": line_id}

@app.get("/api/audit")
def get_audit_trail(quote_id: str):
    with get_db() as conn:
        return fetch_audit_trail(conn, "quote", quote_id)
