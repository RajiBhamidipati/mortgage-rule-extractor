# Mortgage Policy Rule Extractor

An AI-powered tool that extracts structured lending rules from mortgage policy documents (PDF/Word), validates them through a multi-layered guardrail system, and exports human-reviewed decision tables. Built as a proof-of-concept for automating the translation of unstructured lender criteria into machine-readable rules.

**EU AI Act Classification: HIGH RISK** — All extracted rules require human review before export. No automated lending decisions are made.

---

## The Problem

Mortgage lenders publish their lending criteria as dense, unstructured PDF or Word documents — often 30+ pages of nested tables, footnotes, exceptions, and ambiguous language. Today, translating these into structured decision rules is a manual process that is:

- **Slow** — A single lender document can take days to manually parse and structure
- **Error-prone** — Humans miss rules, misclassify categories, and lose traceability to source text
- **Inconsistent** — Different analysts interpret the same policy language differently
- **Unscalable** — With hundreds of lenders updating criteria quarterly, manual extraction creates a permanent bottleneck

This tool demonstrates that an LLM can extract structured rules from policy documents with source traceability, while a guardrail system catches hallucinations, misclassifications, and regulatory concerns before any rule reaches production.

---

## How It Works

The system follows a five-stage pipeline. Each stage is triggered explicitly by the user — nothing runs automatically.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DOCUMENT INGESTION                               │
│                                                                         │
│   PDF/Word Upload ──► pdfplumber / python-docx ──► Parsed Sections     │
│                        • Section detection         • Tables extracted    │
│                        • Table extraction           • Definitions found  │
│                        • Glossary/acronym capture   • Page tracking      │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        RULE EXTRACTION (Claude)                         │
│                                                                         │
│   Parsed Text + Global Context ──► Claude Sonnet 4.6 ──► JSON Rules    │
│                                                                         │
│   • Structured prompt enforces consistent output schema                 │
│   • Every rule requires a verbatim source_quote from the document       │
│   • Ambiguous language ("typically", "may") → outcome: REFER            │
│   • Table rows → individual rules with conditions                       │
│   • Rule hierarchy: general rules vs specific exceptions                │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        GUARDRAIL CHECKS (5 Layers)                      │
│                                                                         │
│   1. Hallucination Check ─── source_quote verified against document     │
│   2. Completeness Check ──── sections with 0 rules flagged              │
│   3. Classification Validator ── second AI pass on categories           │
│   4. Regulatory Bias Check ── protected characteristics scan            │
│   5. Footnote Check ──────── footnote references verified               │
│                                                                         │
│   Output: Each rule annotated with guardrail flags + reasons            │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        HUMAN REVIEW                                     │
│                                                                         │
│   Per-rule actions: Accept │ Reject │ Edit & Accept │ Flag              │
│   Bulk action: Accept All Unflagged                                     │
│   Full audit trail of every reviewer decision                           │
│                                                                         │
│   ⛔ Export blocked until all flagged rules are resolved                │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        EXPORT                                           │
│                                                                         │
│   Excel Decision Table ──── structured spreadsheet, one row per rule    │
│   NL Statements ─────────── plain-English summary grouped by category   │
│                                                                         │
│   Only APPROVED rules are exported. EU AI Act banner on all outputs.    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Architecture

```
                    ┌──────────────┐
                    │   Browser    │
                    │  React/Vite  │
                    │  port 5173   │
                    └──────┬───────┘
                           │ HTTP
                           ▼
                    ┌──────────────┐         ┌──────────────────┐
                    │   FastAPI    │────────►│   Claude API     │
                    │  port 8000   │◄────────│  (Sonnet 4.6)    │
                    └──────┬───────┘         └──────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ parser.py│ │extractor │ │guardrails│
        │          │ │   .py    │ │   .py    │
        │pdfplumber│ │  Claude  │ │ 5 checks │
        │python-doc│ │ prompt + │ │ + Claude │
        │          │ │ streaming│ │ 2nd pass │
        └──────────┘ └──────────┘ └──────────┘
              │            │            │
              ▼            ▼            ▼
        ┌─────────────────────────────────────┐
        │         In-Memory Session State      │
        │                                      │
        │  SessionState per doc_id:            │
        │  • parsed_text, sections             │
        │  • rules[]                           │
        │  • review_log[] (audit trail)        │
        │  • eval_report                       │
        └──────────────┬──────────────────────┘
                       │
              ┌────────┼────────┐
              ▼                 ▼
        ┌──────────┐     ┌──────────┐
        │outputs.py│     │evaluator │
        │          │     │   .py    │
        │ Excel    │     │ Golden   │
        │ NL Text  │     │ dataset  │
        └──────────┘     └──────────┘
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 7, Tailwind CSS 4, Lucide icons |
| Backend | Python 3, FastAPI, Uvicorn |
| AI | Claude Sonnet 4.6 via Anthropic SDK (streaming) |
| PDF parsing | pdfplumber |
| Word parsing | python-docx |
| Excel export | openpyxl |
| Storage | In-memory (session-based, no database) |

---

## Data Model

Every extracted rule follows a structured schema designed for traceability and decision-engine compatibility.

### ExtractedRule

| Field | Type | Description |
|-------|------|-------------|
| `rule_id` | string | Unique ID with category prefix (e.g., `LTV_001`, `CRD_003`) |
| `category` | enum | `ltv`, `income`, `employment`, `credit`, `property`, `affordability`, `applicant`, `loan` |
| `field` | string | The specific data field tested (e.g., `max_ltv`, `min_income_single`) |
| `operator` | string | `<=`, `>=`, `==`, `IN`, `NOT IN`, `BETWEEN` |
| `value` | string | The threshold or permitted value(s) |
| `unit` | string? | `%`, `£`, `years`, `months`, etc. |
| `conditions` | object? | Qualifying context, e.g., `{"property_type": "new_build"}` |
| `outcome` | string | `PASS`, `REFER`, or `DECLINE` |
| `failure_outcome` | string? | What happens when the rule fails: `REFER` or `DECLINE` |
| `nl_statement` | string | Human-readable rule statement |
| `source_quote` | string | **Verbatim text from the original document** (non-negotiable) |
| `source_section` | string? | Section heading where the rule was found |
| `source_page` | int? | Page number (PDF only) |
| `condition_logic` | string? | Full IF/THEN expression, e.g., `IF property_type == 'HMO' THEN max_ltv = 70%` |
| `precedence` | int | Priority level (higher overrides lower) |
| `rule_scope` | enum | `general` (base rule) or `specific_exception` (narrower override) |
| `overrides_rule_id` | string? | For exceptions: the ID of the general rule being overridden |
| `footnote_ref` | string? | Footnote or asterisk reference text |
| `canonical_field` | string? | Normalised field name from canonical dictionary |
| `canonical_category` | string? | Normalised category from canonical dictionary |
| `status` | enum | `pending_review`, `approved`, `rejected`, `flagged_regulatory`, `flagged_uncertain` |
| `guardrail_flags` | list | Array of `{type, reason}` flags from guardrail checks |

### Rule Hierarchy

When multiple rules apply to the same field (e.g., LTV limits), the system captures precedence:

```
LTV_001 (general):        max_ltv <= 95%    precedence: 1
LTV_004 (exception):      max_ltv <= 85%    precedence: 2, conditions: {property_type: "new_build"}
LTV_005 (exception):      max_ltv <= 70%    precedence: 3, conditions: {property_type: "HMO"}
```

Higher-precedence specific exceptions override general rules when their conditions are met.

### Canonical Dictionary

A standardised mapping normalises lender-specific terminology to consistent field names:

```
"maximum LTV"     → max_ltv (canonical: maximum_loan_to_value)
"income multiple"  → max_income_multiple_single
"min credit score" → min_credit_score
```

This enables cross-lender comparison when the same canonical field is extracted from different policy documents.

---

## Guardrails

Guardrails are automated validation checks that run after extraction and before human review. They are the primary safety mechanism for a HIGH RISK AI system — they catch errors the LLM makes before a human reviewer has to find them manually.

### 1. Hallucination Check

**What it does:** Verifies that every rule's `source_quote` exists in the original document text.

**Why it matters:** LLMs can paraphrase, merge, or invent text that wasn't in the source. In a compliance context, a rule that can't be traced to source text is worthless.

**How it works:**
- Exact string match against the full document text
- Normalised match (collapse whitespace, case-insensitive) for minor formatting differences
- Substring match on the first 60 characters for PDF extraction artefacts

**Flag type:** `HALLUCINATION` — "source_quote not found in document text"

### 2. Completeness Check

**What it does:** Identifies document sections that have substantial text content but zero extracted rules.

**Why it matters:** A section about "Interest Only Lending Criteria" with 500 characters but no rules likely means the AI skipped something important.

**How it works:**
- Maps each document section to its extracted rule count
- Flags sections with >200 characters and 0 rules
- Ignores boilerplate sections (table of contents, glossary, disclaimers, etc.)

**Output:** Session-level warnings, not per-rule flags

### 3. Classification Validator

**What it does:** A second Claude pass reviews every rule's category assignment.

**Why it matters:** A rule about "maximum age at end of mortgage term" could be classified as `applicant` or `loan`. Misclassification breaks downstream decision logic.

**How it works:**
- Sends compact rule summaries (ID, category, field, NL statement) to Claude
- Claude returns: `is_correct`, `suggested_category`, `reason` for each rule
- Disagreements are flagged, not auto-corrected — the human reviewer decides

**Flag type:** `MISCLASSIFIED_CANDIDATE` — "Category 'ltv' may be 'loan': [reason]"

### 4. Regulatory Bias Check

**What it does:** Scans rules for references to protected characteristics and FCA MCOB concerns.

**Why it matters:** Under the Equality Act 2010 and FCA MCOB rules, lending criteria that reference protected characteristics (race, gender, religion, disability, etc.) require compliance review. Some references are legitimate (e.g., "minimum age 18") while others are red flags.

**What it scans for:**

| Protected Characteristics | FCA MCOB Keywords |
|--------------------------|-------------------|
| age, gender, sex, race, ethnicity | treating customers fairly, TCF |
| religion, disability, marital status | conduct risk, vulnerable customer |
| pregnancy, sexual orientation | affordability assessment |
| nationality, national origin | automatic decline, blanket decline |

**Legitimate exceptions:** Standard lending terms like "maximum age at end of mortgage term" are flagged but noted as likely legitimate. Rules referencing other protected characteristics are flagged as `REGULATORY_BIAS` and the rule status is set to `flagged_regulatory`.

### 5. Footnote Check

**What it does:** Verifies that footnote references (`*`, `†`, `1.`, etc.) in extracted rules can be traced back to actual footnote text in the document.

**Why it matters:** Footnotes often contain critical caveats ("*subject to individual assessment") that change a rule's interpretation.

**Flag type:** `FOOTNOTE_UNVERIFIED` — "Footnote reference could not be verified in document text"

### Guardrail Flag Types Summary

| Flag Type | Source Check | Severity |
|-----------|-------------|----------|
| `HALLUCINATION` | Check 1 | High — rule may be fabricated |
| `COMPLETENESS` | Check 2 | Medium — section may have missed rules |
| `MISCLASSIFIED_CANDIDATE` | Check 3 | Medium — category may be wrong |
| `REGULATORY_BIAS` | Check 4 | High — requires compliance review |
| `FCA_MCOB_CONCERN` | Check 4 | High — FCA-relevant keyword detected |
| `MANUAL_LOGIC_REQUIRED` | Extraction | Medium — ambiguous source language |
| `FOOTNOTE_UNVERIFIED` | Check 5 | Low — footnote couldn't be traced |
| `UNMAPPED_TERM` | Canonical mapping | Low — field not in canonical dictionary |

---

## Evaluation Framework

The evaluation system measures extraction quality against a hand-verified **golden dataset** — a set of rules that are known to exist in a reference document.

### Metrics

| Metric | Formula | What It Measures | POC Target |
|--------|---------|-----------------|------------|
| **Precision** | TP / (TP + FP) | Of the rules extracted, how many are correct? | ≥ 80% |
| **Recall** | TP / (TP + FN) | Of the expected rules, how many were found? | ≥ 80% |
| **F1 Score** | 2 × (P × R) / (P + R) | Balance of precision and recall | ≥ 80% |
| **Source Fidelity** | Verified quotes / Total rules | How many source quotes exist in the document? | ≥ 90% |
| **Classification Accuracy** | Correct categories / Matched rules | For matched rules, is the category right? | — |
| **EQS** | Weighted composite (0–100) | Overall Extraction Quality Score | ≥ 80 |

### EQS Calculation

```
EQS = (0.30 × Precision) + (0.30 × Recall) + (0.25 × Classification) + (0.15 × Source Fidelity)
```

Scaled to 0–100. The weighting reflects that finding the right rules (precision + recall) matters most, followed by correct classification, then source traceability.

### RAG Status

| Status | EQS Range | Interpretation |
|--------|-----------|---------------|
| Green | ≥ 85 | Extraction quality is strong, ready for scaling |
| Amber | 70–84 | Acceptable but prompt tuning recommended |
| Red | < 70 | Significant gaps — review prompt, parsing, or document quality |

### Matching Strategy

Rules are matched between the golden dataset and extracted rules by `(category, field)` tuple, case-insensitive. This means a rule is a "true positive" if the AI extracted a rule with the same category and field as one in the golden set.

### Golden Dataset

The reference golden dataset contains 31 hand-verified rules across all 8 categories:

| Category | Golden Rules | Examples |
|----------|-------------|----------|
| LTV | 7 | max_ltv (95%), max_ltv_btl (80%), max_ltv_new_build (85%) |
| Income | 4 | min_income_single (£25,000), max_income_multiple (4.5x) |
| Employment | 5 | min_tenure (6 months), self_employed_history (2 years) |
| Credit | 4 | min_credit_score (620), ccj_lookback (6 years) |
| Property | 3 | min_value (£75,000), min_lease_term (70 years) |
| Affordability | 2 | stress_test_rate (3%), max_dti_ratio (45%) |
| Applicant | 3 | min_age (18), max_age_at_term_end (75) |
| Loan | 3 | min_term (5 years), max_term (35 years) |

---

## Human Review Workflow

Every rule goes through a mandatory review cycle before it can be exported. This is a core requirement of the EU AI Act HIGH RISK classification.

### Per-Rule Actions

| Action | Effect | When to Use |
|--------|--------|-------------|
| **Accept** | Status → `approved` | Rule is correct as extracted |
| **Reject** | Status → `rejected` | Rule is wrong, fabricated, or duplicate |
| **Edit & Accept** | Edit fields, then → `approved` | Rule is mostly right but needs correction |
| **Flag Regulatory** | Status → `flagged_regulatory` | Needs compliance team review |
| **Flag Uncertain** | Status → `flagged_uncertain` | Ambiguous, needs domain expert |

### Bulk Actions

- **Accept All Unflagged** — Approves all `pending_review` rules that have zero guardrail flags

### Audit Trail

Every reviewer action is logged with:
- `rule_id`, `action`, `reviewed_by`, `reviewed_at`
- `previous_status` → `new_status`
- `edits` (if fields were modified)
- `comments` (optional)

### Export Gating

Export is **blocked** until:
1. Guardrails have been run
2. No rules remain in `flagged_regulatory` status
3. No rules remain in `flagged_uncertain` status
4. At least one rule is `approved`

---

## Export Formats

### Excel Decision Table

A structured `.xlsx` workbook with one row per approved rule. Designed for import into lending decision engines.

**Columns (21):** Rule ID, Category, Field, Operator, Value, Unit, Conditions, Condition Logic, Outcome, Failure Outcome, NL Statement, Source Quote, Source Section, Source Page, Precedence, Rule Scope, Overrides Rule, Footnote, Canonical Field, Canonical Category, Status

**Styling:**
- Status-based row colouring (green = approved, red = rejected, amber = flagged)
- Frozen header row
- EU AI Act compliance banner in metadata row

### Natural Language Statements

A plain-text `.txt` file with human-readable rule summaries grouped by category. Useful for compliance review, documentation, and sharing with non-technical stakeholders.

```
## LTV
----
  LTV_001: Maximum LTV for standard residential mortgages is 95%
    Source: 1. Loan-to-Value (LTV) Requirements, p.2

  LTV_002: Maximum LTV for buy-to-let properties is 80%
    Conditions: property_type=buy_to_let
    Source: 1. Loan-to-Value (LTV) Requirements, p.2
```

---

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/upload` | Upload and parse PDF/DOCX |
| `POST` | `/api/extract/{doc_id}` | Run Claude extraction |
| `POST` | `/api/guardrails/{doc_id}` | Run all 5 guardrail checks |
| `GET` | `/api/rules/{doc_id}` | Fetch all rules for a document |
| `PATCH` | `/api/rules/{doc_id}/{rule_id}` | Update rule status (reviewer action) |
| `POST` | `/api/evaluate/{doc_id}` | Run evaluation against golden dataset |
| `GET` | `/api/status/{doc_id}` | Check export eligibility and rule counts |
| `GET` | `/api/export/excel/{doc_id}` | Download Excel decision table |
| `GET` | `/api/export/text/{doc_id}` | Download NL text summary |
| `GET` | `/api/review-log/{doc_id}` | Full audit trail of reviewer actions |

---

## Project Structure

```
mortgage-rule-extractor/
├── backend/
│   ├── main.py              # FastAPI app, all endpoints, session management
│   ├── parser.py            # PDF/Word parsing, section detection, table extraction
│   ├── extractor.py         # Claude API integration, extraction prompt, streaming
│   ├── guardrails.py        # 5 guardrail checks (hallucination, completeness, etc.)
│   ├── evaluator.py         # Golden dataset comparison, metrics calculation
│   ├── outputs.py           # Excel and NL text export, export gating
│   ├── schema.py            # Pydantic models (ExtractedRule, EvalReport, etc.)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Main workflow orchestrator
│   │   └── components/
│   │       ├── FileUpload.jsx       # Drag-and-drop document upload
│   │       ├── RuleTable.jsx        # Rule review table with filters and actions
│   │       ├── EvalDashboard.jsx    # Evaluation metrics display
│   │       ├── ExportPanel.jsx      # Export controls with gating
│   │       └── RegulatoryBanner.jsx # EU AI Act compliance banner
│   └── package.json
├── canonical/
│   └── dictionary.json      # Canonical field name mapping (26 standardised fields)
├── evals/
│   ├── golden_dataset.json  # 31 hand-verified reference rules
│   └── eval_reports/        # Saved evaluation results
├── model_card/
│   └── MODEL_CARD.md        # AI model documentation (EU AI Act)
├── sample_docs/             # Sample mortgage policy documents for testing
└── CLAUDE.md                # AI assistant instructions
```

---

## Limitations & Known Issues

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| Complex merged table cells | May not parse correctly from PDF | Tables wrapped in `[TABLE]` markers; human review catches gaps |
| Ambiguous policy language | "Typically", "may", "at discretion" can't be structured | Extracted as `REFER` outcome with `MANUAL_LOGIC_REQUIRED` flag |
| Large documents (>50 pages) | May approach Claude context limits | Streaming API used; truncated responses are auto-repaired |
| In-memory session storage | State lost on server restart | POC scope — production would use persistent storage |
| Single-document evaluation | Golden dataset covers one reference doc | Framework supports adding golden datasets per document |
| Keyword-based regulatory check | Not a legal determination | Heuristic scan flags for human compliance review, not auto-reject |

---

## Model Card

See [model_card/MODEL_CARD.md](model_card/MODEL_CARD.md) for full AI model documentation including:
- Intended use and out-of-scope applications
- EU AI Act compliance measures
- Performance targets and known limitations
- Bias considerations and mitigation strategies

---

*POC v0.1 — March 2026 | Author: Raji Bhamidipati, Senior AI PM*
