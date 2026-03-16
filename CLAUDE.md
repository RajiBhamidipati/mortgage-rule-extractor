# Mortgage Policy Rule Extractor — CLAUDE.md

## Project Overview
AI-powered tool that extracts structured lending rules from mortgage policy documents (PDF/Word).
EU AI Act HIGH RISK classification — all extracted rules require human review before export.

## Stack
- Backend: Python 3 + FastAPI (port 8000)
- Frontend: React 19 + Vite 7 + Tailwind CSS 4 (port 5173)
- AI (extraction): Claude Sonnet 4.6 via anthropic SDK (parallel streaming, 8 workers)
- AI (classification guardrail): Claude Haiku 4.5 (lightweight validation)
- Storage: In-memory (session-based, no database)
- Deployment: Railway (Docker, single-service) — https://mortgage-rule-extractor-production.up.railway.app

## Quick Start
```bash
# Backend
cd backend
source ../.venv/bin/activate
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm run dev
```

## Key Commands
```bash
# Install backend deps
cd backend && pip install -r requirements.txt

# Install frontend deps
cd frontend && npm install

# Build frontend for production
cd frontend && npm run build
```

## Architecture
1. Document Ingestion → parser.py (pdfplumber + python-docx)
2. Rule Extraction → extractor.py (parallel chunked, 8 concurrent Claude API calls per document)
3. Field Normalisation → extractor.py (canonical dictionary maps field names to standardised forms)
4. Guardrails → guardrails.py (hallucination, completeness, classification via Haiku, regulatory, footnotes)
5. Validation UI → React frontend (accept/reject/edit/flag per rule, card-based layout)
6. Evaluation → evaluator.py (precision/recall/F1 vs golden dataset, fuzzy field matching)
7. Export → outputs.py (Excel decision table + NL text, gated by flag resolution)

## Extraction Strategy
- Document split into sections, boilerplate auto-skipped
- Each section sent to Claude Sonnet 4.6 in parallel (up to 8 workers)
- Canonical field vocabulary (30 names from canonical/dictionary.json) enforced in prompt
- Post-extraction: field normalisation → de-duplication → renumbering
- Truncated JSON responses auto-repaired

## API Endpoints
- POST /api/upload — upload PDF/Word file
- POST /api/extract/{doc_id} — run Claude extraction (parallel chunked)
- POST /api/guardrails/{doc_id} — run 5 guardrail checks
- GET /api/rules/{doc_id} — get all rules
- PATCH /api/rules/{doc_id}/{rule_id} — update rule status
- POST /api/evaluate/{doc_id} — run eval against golden dataset
- GET /api/status/{doc_id} — check export eligibility
- GET /api/export/excel/{doc_id} — download Excel
- GET /api/export/text/{doc_id} — download NL text
- GET /api/review-log/{doc_id} — audit trail

## Key Files
- backend/extractor.py — parallel chunked extraction with canonical field vocab
- backend/guardrails.py — 5 guardrail checks (Haiku for classification)
- backend/evaluator.py — golden dataset comparison with fuzzy field matching
- canonical/dictionary.json — 30 standardised field names with aliases
- evals/golden_dataset.json — 31 hand-verified reference rules

## No tests exist in this project yet.
