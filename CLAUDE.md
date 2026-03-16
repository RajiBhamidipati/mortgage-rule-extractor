# Mortgage Policy Rule Extractor — CLAUDE.md

## Project Overview
AI-powered tool that extracts structured lending rules from mortgage policy documents (PDF/Word).
EU AI Act HIGH RISK classification — all extracted rules require human review before export.

## Stack
- Backend: Python 3 + FastAPI (port 8000)
- Frontend: React + Vite + Tailwind CSS (port 5173)
- AI: Claude API (claude-sonnet-4-6) via anthropic SDK
- Storage: In-memory (session-based, no database)

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
```

## Architecture
1. Document Ingestion → parser.py (pdfplumber + python-docx)
2. Rule Extraction → extractor.py (Claude API structured prompt)
3. Guardrails → guardrails.py (hallucination, completeness, classification, regulatory)
4. Validation UI → React frontend (accept/reject/edit/flag per rule)
5. Export → outputs.py (Excel decision table + NL text)

## API Endpoints
- POST /api/upload — upload PDF/Word file
- POST /api/extract/{doc_id} — run Claude extraction
- POST /api/guardrails/{doc_id} — run guardrail checks
- GET /api/rules/{doc_id} — get all rules
- PATCH /api/rules/{doc_id}/{rule_id} — update rule status
- POST /api/evaluate/{doc_id} — run eval against golden dataset
- GET /api/export/excel/{doc_id} — download Excel
- GET /api/export/text/{doc_id} — download NL text

## No tests exist in this project yet.
