"""Rule extraction using Claude API.

Sends parsed document text to Claude with a structured extraction prompt
and returns a list of ExtractedRule objects. Implements PRD F-05 through F-08c.
"""

import json
import os
import re
from datetime import datetime, timezone

import anthropic

from schema import (
    ExtractedRule, ExtractionResult, GuardrailFlag,
    RuleCategory, RuleStatus, RuleScope,
)

client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

MODEL = "claude-sonnet-4-6"

EXTRACTION_PROMPT = """You are a mortgage lending policy analyst specialising in extracting structured rules from lender criteria documents.

## TASK
Extract ALL lending rules from the document text below. Be exhaustive — every threshold, limit, condition, requirement, and eligibility criterion is a rule.

## GLOBAL CONTEXT
{global_context}

## OUTPUT FORMAT
Return a JSON array. Each element must have ALL of these fields:

```json
{{
  "rule_id": "string — sequential: LTV_001, INC_001, EMP_001, CRD_001, PROP_001, AFF_001, APP_001, LOAN_001 etc.",
  "category": "string — one of: ltv, income, employment, credit, property, affordability, applicant, loan",
  "field": "string — the specific data field tested, e.g. max_ltv, min_income, employment_type",
  "operator": "string — one of: <=, >=, ==, IN, NOT IN, BETWEEN",
  "value": "string — the threshold or allowed value(s)",
  "unit": "string or null — %, £, years, months, etc.",
  "conditions": "object or null — qualifying context e.g. {{\\"property_type\\": \\"new_build\\"}}",
  "outcome": "string — PASS, REFER, or DECLINE",
  "failure_outcome": "string — REFER or DECLINE",
  "nl_statement": "string — clear English rule statement",
  "source_quote": "string — EXACT VERBATIM text from the document. Copy word-for-word. Do not paraphrase.",
  "source_section": "string — section heading this rule appears under",
  "source_page": "integer or null",
  "condition_logic": "string or null — full IF/THEN expression, e.g. IF property_type == 'HMO' THEN max_ltv = 70%",
  "precedence": "integer — 1 = lowest priority, higher = overrides lower",
  "rule_scope": "string — 'general' for base rules, 'specific_exception' for narrower overrides",
  "overrides_rule_id": "string or null — if specific_exception, the rule_id of the general rule it overrides",
  "footnote_ref": "string or null — any asterisk or footnote reference"
}}
```

## CRITICAL INSTRUCTIONS

1. **EVERY rule must have a verbatim source_quote** copied exactly from the document. This is non-negotiable.

2. **Rule scope classification (F-08b):** When multiple rules apply to the same field (e.g. LTV):
   - The broadest rule is scope: "general" with lower precedence
   - Narrower exceptions are scope: "specific_exception" with higher precedence and overrides_rule_id set
   - If you cannot determine the hierarchy, set both to "general" — the guardrail system will flag conflicts

3. **Ambiguous language (F-08):** If the source text uses vague language like "typically", "may", "in most cases", "considered on a case-by-case basis", "at the lender's discretion":
   - Still extract the rule
   - Set the outcome to "REFER"
   - Add a note in condition_logic: "MANUAL_LOGIC_REQUIRED: [exact vague phrase]"

4. **Footnotes (F-12b):** If a value in a table has an asterisk (*) or numeric footnote, capture the footnote text in footnote_ref.

5. **Be exhaustive:** Extract EVERY rule, including implicit ones. A statement like "applicants must be 18+" is a rule. Missing a rule is worse than extracting a borderline one.

6. **Tables:** Treat each row of a criteria table as a separate rule unless rows are clearly sub-conditions of a single rule.

## DOCUMENT TEXT
{document_text}

Return ONLY the JSON array. No markdown fences, no explanation, no commentary."""


def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences if Claude wraps the response."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _repair_truncated_json(text: str) -> str:
    """Attempt to recover a valid JSON array from a truncated response.

    Finds the last complete object (ending with '}') and closes the array.
    """
    # Find the last complete JSON object boundary
    last_brace = text.rfind("}")
    if last_brace == -1:
        return text
    truncated = text[: last_brace + 1]
    # Remove any trailing comma
    truncated = truncated.rstrip().rstrip(",")
    # Close the array
    if not truncated.endswith("]"):
        truncated += "\n]"
    return truncated


def _build_global_context(definitions: list[str]) -> str:
    """Build the Global Context Summary from extracted definitions (F-03)."""
    if not definitions:
        return "No definitions or acronyms found in this document."
    lines = ["The following definitions and acronyms are used throughout this document:"]
    for d in definitions:
        lines.append(f"  - {d}")
    return "\n".join(lines)


def _category_prefix(category: str) -> str:
    """Return the ID prefix for a rule category."""
    prefixes = {
        "ltv": "LTV", "income": "INC", "employment": "EMP",
        "credit": "CRD", "property": "PROP", "affordability": "AFF",
        "applicant": "APP", "loan": "LOAN",
    }
    return prefixes.get(category, "RULE")


def extract_rules(
    full_text: str,
    doc_name: str,
    doc_id: str,
    definitions: list[str] | None = None,
) -> ExtractionResult:
    """Extract rules from document text using Claude API.

    Args:
        full_text: Complete document text
        doc_name: Source filename
        doc_id: Unique document identifier
        definitions: Global context definitions (F-03)

    Returns:
        ExtractionResult with list of ExtractedRule objects
    """
    global_context = _build_global_context(definitions or [])

    prompt = EXTRACTION_PROMPT.format(
        global_context=global_context,
        document_text=full_text,
    )

    # Use streaming for long requests (required by Anthropic API for >10min ops)
    raw_text = ""
    stop_reason = None
    with client.messages.stream(
        model=MODEL,
        max_tokens=16384,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            raw_text += text
        stop_reason = stream.get_final_message().stop_reason

    raw_text = _strip_json_fences(raw_text)

    # If response was truncated, try to salvage valid JSON
    if stop_reason == "max_tokens":
        raw_text = _repair_truncated_json(raw_text)

    rules_data = json.loads(raw_text)

    rules: list[ExtractedRule] = []
    for r in rules_data:
        # Ensure required fields have defaults
        r.setdefault("policy_doc_id", doc_id)
        r.setdefault("doc_name", doc_name)
        r.setdefault("version", "1.0")
        r.setdefault("status", "pending_review")
        r.setdefault("guardrail_flags", [])
        r.setdefault("rule_scope", "general")
        r.setdefault("unit", None)
        r.setdefault("conditions", None)
        r.setdefault("failure_outcome", None)
        r.setdefault("source_page", None)
        r.setdefault("condition_logic", None)
        r.setdefault("precedence", 1)
        r.setdefault("overrides_rule_id", None)
        r.setdefault("footnote_ref", None)

        # Convert guardrail_flags from raw dicts/strings to GuardrailFlag objects
        raw_flags = r.get("guardrail_flags", [])
        parsed_flags = []
        for f in raw_flags:
            if isinstance(f, dict):
                parsed_flags.append(GuardrailFlag(**f))
            elif isinstance(f, str):
                parsed_flags.append(GuardrailFlag(type="EXTRACTION_NOTE", reason=f))
        r["guardrail_flags"] = parsed_flags

        # Check for ambiguous language → flag as MANUAL_LOGIC_REQUIRED (F-08c)
        cl = r.get("condition_logic") or ""
        if "MANUAL_LOGIC_REQUIRED" in cl:
            parsed_flags.append(GuardrailFlag(
                type="MANUAL_LOGIC_REQUIRED",
                reason=f"Rule contains vague language requiring human interpretation: {cl}",
            ))
            r["status"] = "flagged_uncertain"

        try:
            rule = ExtractedRule(**r)
            rules.append(rule)
        except Exception as e:
            # Log but don't crash — partial extraction is better than none
            print(f"Warning: skipping rule {r.get('rule_id', '?')}: {e}")

    # Collect sections that produced rules
    sections_with_rules = set(r.source_section for r in rules if r.source_section)

    return ExtractionResult(
        rules=rules,
        doc_name=doc_name,
        doc_id=doc_id,
        extraction_timestamp=datetime.now(timezone.utc).isoformat(),
        model_used=MODEL,
        total_rules_extracted=len(rules),
        sections_processed=list(sections_with_rules),
    )
