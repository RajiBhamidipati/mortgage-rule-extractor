"""FastAPI application — Mortgage Policy Rule Extractor.

All state is held in-memory (sessions dict). No database.
Run: uvicorn main:app --reload --port 8000
"""

import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Add backend dir to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from schema import (
    ExtractedRule, ExtractionResult, SessionState,
    RuleUpdateRequest, ReviewAction, RuleStatus, EvalReport,
)
from parser import parse_document
from extractor import extract_rules
from guardrails import run_all_guardrails
from evaluator import run_evaluation
from outputs import generate_excel, generate_nl_text, can_export

app = FastAPI(
    title="Mortgage Policy Rule Extractor",
    version="0.1.0",
    description="AI-powered extraction of structured lending rules from policy documents. EU AI Act HIGH RISK.",
)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store
sessions: dict[str, SessionState] = {}

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DATASET_PATH = PROJECT_ROOT / "evals" / "golden_dataset.json"
UPLOAD_DIR = PROJECT_ROOT / "backend" / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


# ── Health Check ──

@app.get("/api/health")
async def health():
    return {"status": "ok", "sessions": len(sessions)}


# ── Upload (F-01) ──

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a PDF or Word document for rule extraction."""
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = file.filename.lower().split(".")[-1]
    if ext not in ("pdf", "docx"):
        raise HTTPException(400, f"Unsupported file type: .{ext}. Supported: .pdf, .docx")

    doc_id = str(uuid.uuid4())[:8]

    # Save to temp location
    file_path = UPLOAD_DIR / f"{doc_id}.{ext}"
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Parse document
    try:
        parsed = parse_document(str(file_path), file.filename)
    except Exception as e:
        raise HTTPException(500, f"Failed to parse document: {e}")

    # Create session
    session = SessionState(
        doc_id=doc_id,
        doc_name=file.filename,
        doc_type=ext,
        upload_timestamp=datetime.now(timezone.utc).isoformat(),
        parsed_text=parsed.full_text,
        sections=[
            {
                "heading": s.section_heading,
                "char_count": s.char_count,
                "page": s.page,
                "has_tables": len(s.tables) > 0 if hasattr(s, "tables") else False,
            }
            for s in parsed.sections
        ],
    )
    # Store parsed doc for guardrails (attach to session as extra)
    session._parsed_doc = parsed  # type: ignore[attr-defined]
    sessions[doc_id] = session

    return {
        "doc_id": doc_id,
        "doc_name": file.filename,
        "doc_type": ext,
        "section_count": len(parsed.sections),
        "char_count": len(parsed.full_text),
        "sections": session.sections,
        "definitions_found": len(parsed.definitions),
    }


# ── Extract Rules (F-05) ──

@app.post("/api/extract/{doc_id}")
async def extract(doc_id: str):
    """Run Claude extraction on the uploaded document."""
    session = _get_session(doc_id)
    parsed_doc = getattr(session, "_parsed_doc", None)

    definitions = parsed_doc.definitions if parsed_doc else []

    try:
        result = extract_rules(
            full_text=session.parsed_text,
            doc_name=session.doc_name,
            doc_id=doc_id,
            definitions=definitions,
        )
    except Exception as e:
        raise HTTPException(500, f"Extraction failed: {e}")

    session.rules = result.rules
    session.extraction_done = True

    return {
        "doc_id": doc_id,
        "total_rules_extracted": result.total_rules_extracted,
        "model_used": result.model_used,
        "extraction_timestamp": result.extraction_timestamp,
        "sections_with_rules": result.sections_processed,
        "rules": [r.model_dump(mode="json") for r in result.rules],
    }


# ── Run Guardrails (F-09 through F-13) ──

@app.post("/api/guardrails/{doc_id}")
async def run_guardrails(doc_id: str):
    """Run all four guardrail checks on extracted rules."""
    session = _get_session(doc_id)

    if not session.extraction_done:
        raise HTTPException(400, "Must run extraction before guardrails")

    parsed_doc = getattr(session, "_parsed_doc", None)
    if not parsed_doc:
        raise HTTPException(500, "Parsed document not found in session")

    try:
        session.rules, completeness_warnings = run_all_guardrails(
            rules=session.rules,
            parsed_doc=parsed_doc,
        )
    except Exception as e:
        raise HTTPException(500, f"Guardrails failed: {e}")

    session.completeness_warnings = completeness_warnings
    session.guardrails_done = True

    # Summary
    flagged_count = sum(1 for r in session.rules if r.guardrail_flags)
    regulatory_count = sum(
        1 for r in session.rules
        if r.status == RuleStatus.FLAGGED_REGULATORY
    )
    uncertain_count = sum(
        1 for r in session.rules
        if r.status == RuleStatus.FLAGGED_UNCERTAIN
    )

    return {
        "doc_id": doc_id,
        "total_rules": len(session.rules),
        "rules_with_flags": flagged_count,
        "regulatory_flags": regulatory_count,
        "uncertainty_flags": uncertain_count,
        "completeness_warnings": completeness_warnings,
        "rules": [r.model_dump(mode="json") for r in session.rules],
    }


# ── Get Rules ──

@app.get("/api/rules/{doc_id}")
async def get_rules(doc_id: str):
    """Get all rules for a document."""
    session = _get_session(doc_id)
    return {
        "doc_id": doc_id,
        "total_rules": len(session.rules),
        "rules": [r.model_dump(mode="json") for r in session.rules],
    }


# ── Update Rule (F-15, F-16) ──

@app.patch("/api/rules/{doc_id}/{rule_id}")
async def update_rule(doc_id: str, rule_id: str, update: RuleUpdateRequest):
    """Update a rule's status (accept, reject, edit, flag)."""
    session = _get_session(doc_id)

    rule = next((r for r in session.rules if r.rule_id == rule_id), None)
    if not rule:
        raise HTTPException(404, f"Rule {rule_id} not found")

    previous_status = rule.status

    # Apply edits if provided
    if update.edits:
        for field_name, value in update.edits.items():
            if hasattr(rule, field_name):
                setattr(rule, field_name, value)

    # Apply status change
    if update.status:
        rule.status = update.status

    # Set reviewer info
    rule.reviewed_by = update.reviewed_by or "anonymous"
    rule.reviewed_at = datetime.now(timezone.utc)

    # Log review action (F-16)
    action = ReviewAction(
        rule_id=rule_id,
        action=update.status.value if update.status else "edit",
        reviewed_by=rule.reviewed_by,
        reviewed_at=rule.reviewed_at,
        previous_status=previous_status,
        new_status=rule.status,
        edits=update.edits,
        comments=update.comments,
    )
    session.review_log.append(action)

    return {
        "rule_id": rule_id,
        "status": rule.status.value,
        "reviewed_by": rule.reviewed_by,
        "reviewed_at": rule.reviewed_at.isoformat(),
    }


# ── Evaluate (F-20 through F-23) ──

@app.post("/api/evaluate/{doc_id}")
async def evaluate(doc_id: str):
    """Run evaluation against golden dataset."""
    session = _get_session(doc_id)

    if not session.extraction_done:
        raise HTTPException(400, "Must run extraction before evaluation")

    if not GOLDEN_DATASET_PATH.exists():
        raise HTTPException(404, "Golden dataset not found at evals/golden_dataset.json")

    try:
        report = run_evaluation(
            extracted_rules=session.rules,
            golden_path=str(GOLDEN_DATASET_PATH),
            doc_text=session.parsed_text,
            doc_id=doc_id,
            doc_name=session.doc_name,
        )
    except Exception as e:
        raise HTTPException(500, f"Evaluation failed: {e}")

    session.eval_report = report

    return report.model_dump(mode="json")


# ── Export Status (F-17, F-27) ──

@app.get("/api/status/{doc_id}")
async def export_status(doc_id: str):
    """Check if export is allowed."""
    session = _get_session(doc_id)
    exportable, blockers = can_export(session.rules)
    return {
        "doc_id": doc_id,
        "can_export": exportable,
        "blocking_reasons": blockers,
        "total_rules": len(session.rules),
        "approved_rules": sum(1 for r in session.rules if r.status == RuleStatus.APPROVED),
        "pending_rules": sum(1 for r in session.rules if r.status == RuleStatus.PENDING_REVIEW),
        "rejected_rules": sum(1 for r in session.rules if r.status == RuleStatus.REJECTED),
        "flagged_rules": sum(
            1 for r in session.rules
            if r.status in (RuleStatus.FLAGGED_REGULATORY, RuleStatus.FLAGGED_UNCERTAIN)
        ),
    }


# ── Export Excel (F-24, F-26) ──

@app.get("/api/export/excel/{doc_id}")
async def export_excel(doc_id: str):
    """Download Excel decision table of approved rules."""
    session = _get_session(doc_id)

    exportable, blockers = can_export(session.rules)
    if not exportable:
        raise HTTPException(
            400,
            f"Export blocked: {len(blockers)} unresolved flag(s). "
            f"Resolve all regulatory and uncertainty flags before export.",
        )

    # Export only approved rules
    approved = [r for r in session.rules if r.status == RuleStatus.APPROVED]
    if not approved:
        raise HTTPException(400, "No approved rules to export")

    buffer = generate_excel(approved, session.doc_name)

    filename = f"rules_{session.doc_name.replace('.', '_')}_{doc_id}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Export NL Text (F-25) ──

@app.get("/api/export/text/{doc_id}")
async def export_text(doc_id: str):
    """Download NL rule statements as plain text."""
    session = _get_session(doc_id)

    exportable, blockers = can_export(session.rules)
    if not exportable:
        raise HTTPException(
            400,
            f"Export blocked: {len(blockers)} unresolved flag(s).",
        )

    approved = [r for r in session.rules if r.status == RuleStatus.APPROVED]
    if not approved:
        raise HTTPException(400, "No approved rules to export")

    text = generate_nl_text(approved, session.doc_name)
    filename = f"rules_{session.doc_name.replace('.', '_')}_{doc_id}.txt"

    return PlainTextResponse(
        content=text,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Review Log ──

@app.get("/api/review-log/{doc_id}")
async def get_review_log(doc_id: str):
    """Get the audit trail of reviewer actions."""
    session = _get_session(doc_id)
    return {
        "doc_id": doc_id,
        "actions": [a.model_dump(mode="json") for a in session.review_log],
    }


# ── Helper ──

def _get_session(doc_id: str) -> SessionState:
    if doc_id not in sessions:
        raise HTTPException(404, f"Document {doc_id} not found. Upload a document first.")
    return sessions[doc_id]


# ── Serve frontend static build (production) ──

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
