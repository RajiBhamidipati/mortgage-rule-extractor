# Model Card — Mortgage Policy Rule Extractor

## Model Details

| Field | Value |
|-------|-------|
| **Model** | Claude Sonnet 4.6 (claude-sonnet-4-6-20250514) |
| **Task** | Structured rule extraction from mortgage lending policy documents |
| **Version** | POC v0.1 |
| **Date** | March 2026 |
| **Author** | Raji Bhamidipati, Senior AI PM |

## Intended Use

- **Primary use**: Extract structured lending rules from lender policy documents (PDF/Word) for internal review and validation
- **Users**: Business Analysts, Risk/Compliance reviewers, Platform Engineers
- **Context**: Internal POC — demonstrates feasibility of AI-powered rule extraction

## Out of Scope

- Direct production deployment to a live decisioning engine
- Processing of personal applicant data
- Replacement of human compliance review
- Automated lending decisions without human oversight

## EU AI Act Classification

**HIGH RISK** — Credit scoring and automated decisioning in lending are explicitly listed as high-risk AI applications under the EU AI Act.

### Compliance measures built into the POC:
- Human review is mandatory — no rule may be exported without explicit reviewer approval
- Full audit trail of every reviewer action with timestamps
- Regulatory bias flagging for protected characteristics
- EU AI Act / FCA high-risk banner displayed throughout the UI
- Export blocked until all regulatory flags are resolved

## Performance Metrics

*To be updated after first evaluation run.*

| Metric | Target (POC Gate) | Actual |
|--------|-------------------|--------|
| Precision | ≥ 80% | TBD |
| Recall | ≥ 80% | TBD |
| F1 Score | ≥ 80% | TBD |
| Source Fidelity | ≥ 90% | TBD |
| EQS | ≥ 80/100 | TBD |

## Evaluation Methodology

- **Golden dataset**: Manually verified rules from one section of a lender policy document (minimum 25 rules)
- **Matching**: Rules matched by (category, field) pair
- **EQS weighting**: Precision 30%, Recall 30%, Classification 25%, Source Fidelity 15%

## Known Limitations

1. **Complex table extraction**: Merged cells and multi-level tables in PDFs may not parse correctly
2. **Ambiguous policy language**: Rules with vague language ("typically", "may", "case-by-case") are flagged but require human interpretation
3. **Single-lender scope**: POC validated against one lender's document only
4. **Regulatory check is heuristic**: Protected characteristic detection is keyword-based, not a legal determination
5. **Context window limits**: Very large documents may need to be processed in chunks, which can cause cross-section context loss

## Guardrails

| Check | Type | Description |
|-------|------|-------------|
| Hallucination | Automated | Verifies source_quote exists verbatim in document |
| Completeness | Automated | Flags sections with unexpectedly low rule density |
| Classification | AI-assisted | Second Claude pass to verify category assignments |
| Regulatory Bias | Automated | Keyword scan for protected characteristics and FCA MCOB terms |

## Data

- **Input**: Lender policy documents (PDF, Word) — sanitised, no real customer data
- **Output**: Structured JSON rules, Excel decision table, NL text statements
- **Storage**: In-memory only (session-based, no persistence)
- **No training data**: Claude is a pre-trained model; this system uses prompt engineering only

## Ethical Considerations

- Rules extracted by this system could influence lending decisions that affect people's access to housing
- False negatives (missed rules) could lead to incorrect lending decisions
- False positives (hallucinated rules) could create overly restrictive criteria
- The system must never be used as a substitute for human compliance review
