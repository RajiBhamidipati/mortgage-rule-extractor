"""Rule extraction using Claude API — chunked by section.

Sends each document section to Claude individually with global context,
then merges and de-duplicates results. This avoids token-limit truncation
on large documents and improves extraction quality.

Implements PRD F-05 through F-08c.
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
from parser import ParsedDocument, ParsedSection

client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

MODEL = "claude-sonnet-4-6"

SECTION_PROMPT = """You are a mortgage lending policy analyst specialising in extracting structured rules from lender criteria documents.

## TASK
Extract ALL lending rules from the SECTION TEXT below. Be exhaustive — every threshold, limit, condition, requirement, and eligibility criterion is a rule.

## GLOBAL CONTEXT
{global_context}

{prior_rules_context}

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
  "source_quote": "string — EXACT VERBATIM text from the section. Copy word-for-word. Do not paraphrase.",
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

1. **EVERY rule must have a verbatim source_quote** copied exactly from the section text. This is non-negotiable.

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

7. **If this section contains no extractable rules**, return an empty array: []

## SECTION: {section_heading}
{section_text}

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

    Progressively strips from the end until json.loads succeeds,
    falling back to finding the last complete object boundary.
    """
    # Try parsing as-is first
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # Strategy: find the last complete '}, {' boundary and close the array
    # Walk backwards to find the last complete JSON object
    last_brace = text.rfind("}")
    while last_brace > 0:
        candidate = text[: last_brace + 1].rstrip().rstrip(",") + "\n]"
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            last_brace = text.rfind("}", 0, last_brace)

    return text


def _build_global_context(definitions: list[str]) -> str:
    """Build the Global Context Summary from extracted definitions (F-03)."""
    if not definitions:
        return "No definitions or acronyms found in this document."
    lines = ["The following definitions and acronyms are used throughout this document:"]
    for d in definitions:
        lines.append(f"  - {d}")
    return "\n".join(lines)


def _build_prior_rules_context(prior_rules: list[ExtractedRule]) -> str:
    """Build context about rules already extracted from previous sections."""
    if not prior_rules:
        return ""
    summaries = []
    for r in prior_rules:
        summaries.append(f"  - {r.rule_id}: {r.nl_statement} (category: {r.category}, field: {r.field})")
    lines = [
        "## RULES ALREADY EXTRACTED FROM PREVIOUS SECTIONS",
        "The following rules have already been extracted. Do NOT duplicate them.",
        "If this section contains exceptions or overrides to these rules, use overrides_rule_id to link them.",
        "",
    ] + summaries
    return "\n".join(lines)


def _category_prefix(category: str) -> str:
    """Return the ID prefix for a rule category."""
    prefixes = {
        "ltv": "LTV", "income": "INC", "employment": "EMP",
        "credit": "CRD", "property": "PROP", "affordability": "AFF",
        "applicant": "APP", "loan": "LOAN",
    }
    return prefixes.get(category, "RULE")


def _extract_section(
    section: ParsedSection,
    global_context: str,
    prior_rules: list[ExtractedRule],
) -> list[dict]:
    """Extract rules from a single document section via Claude API.

    Returns raw rule dicts (not yet converted to ExtractedRule).
    """
    section_text = section.text
    if section.tables:
        section_text += "\n\n" + "\n".join(section.tables)

    # Skip very short sections unlikely to contain rules
    if len(section_text.strip()) < 50:
        return []

    heading = section.section_heading or "Untitled Section"
    prior_context = _build_prior_rules_context(prior_rules)

    prompt = SECTION_PROMPT.format(
        global_context=global_context,
        prior_rules_context=prior_context,
        section_heading=heading,
        section_text=section_text,
    )

    # Use streaming for long requests
    raw_text = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            raw_text += text

    raw_text = _strip_json_fences(raw_text)
    raw_text = _repair_truncated_json(raw_text)

    try:
        rules_data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        print(f"Warning: failed to parse JSON for section '{heading}': {e}")
        return []

    if not isinstance(rules_data, list):
        return []

    # Inject section metadata
    for r in rules_data:
        if section.page is not None and not r.get("source_page"):
            r["source_page"] = section.page
        if not r.get("source_section"):
            r["source_section"] = heading

    return rules_data


def _deduplicate_rules(all_rule_dicts: list[dict]) -> list[dict]:
    """Remove duplicate rules based on (category, field, value) tuple."""
    seen = set()
    unique = []
    for r in all_rule_dicts:
        key = (
            r.get("category", "").lower(),
            r.get("field", "").lower(),
            str(r.get("value", "")).lower(),
            str(r.get("conditions", "")).lower(),
        )
        if key not in seen:
            seen.add(key)
            unique.append(r)
        else:
            print(f"De-duplicated: {r.get('rule_id', '?')} ({key[0]}:{key[1]}={key[2]})")
    return unique


def _renumber_rules(rule_dicts: list[dict]) -> list[dict]:
    """Re-assign sequential rule IDs grouped by category."""
    counters: dict[str, int] = {}
    for r in rule_dicts:
        cat = r.get("category", "unknown").lower()
        prefix = _category_prefix(cat)
        counters.setdefault(cat, 0)
        counters[cat] += 1
        r["rule_id"] = f"{prefix}_{counters[cat]:03d}"
    return rule_dicts


def extract_rules(
    full_text: str,
    doc_name: str,
    doc_id: str,
    definitions: list[str] | None = None,
    parsed_doc: ParsedDocument | None = None,
) -> ExtractionResult:
    """Extract rules from document text using Claude API.

    If parsed_doc is provided, uses chunked extraction (one section at a time).
    Otherwise falls back to single-pass extraction on full_text.

    Args:
        full_text: Complete document text (used as fallback)
        doc_name: Source filename
        doc_id: Unique document identifier
        definitions: Global context definitions (F-03)
        parsed_doc: Parsed document with sections (for chunked extraction)

    Returns:
        ExtractionResult with list of ExtractedRule objects
    """
    global_context = _build_global_context(definitions or [])

    sections = parsed_doc.sections if parsed_doc else []

    # ── Chunked extraction: one section at a time ──
    all_rule_dicts: list[dict] = []
    extracted_rules: list[ExtractedRule] = []  # For passing as context to next section

    if sections:
        for i, section in enumerate(sections):
            heading = section.section_heading or "Untitled"
            print(f"[{i+1}/{len(sections)}] Extracting from: {heading} ({section.char_count} chars)")

            try:
                section_rules = _extract_section(section, global_context, extracted_rules)
            except Exception as e:
                print(f"Warning: extraction failed for section '{heading}': {e}")
                section_rules = []

            if section_rules:
                all_rule_dicts.extend(section_rules)
                # Build temporary ExtractedRule objects for context passing
                for r in section_rules:
                    try:
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
                        extracted_rules.append(ExtractedRule(**{
                            **r,
                            "guardrail_flags": [],
                        }))
                    except Exception:
                        pass

            print(f"  → {len(section_rules)} rules found")
    else:
        # Fallback: single-pass extraction (original behaviour)
        prompt = SECTION_PROMPT.format(
            global_context=global_context,
            prior_rules_context="",
            section_heading="Full Document",
            section_text=full_text,
        )
        raw_text = ""
        with client.messages.stream(
            model=MODEL,
            max_tokens=32768,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                raw_text += text

        raw_text = _strip_json_fences(raw_text)
        raw_text = _repair_truncated_json(raw_text)
        all_rule_dicts = json.loads(raw_text)

    # ── De-duplicate and renumber ──
    all_rule_dicts = _deduplicate_rules(all_rule_dicts)
    all_rule_dicts = _renumber_rules(all_rule_dicts)

    # ── Convert to ExtractedRule objects ──
    rules: list[ExtractedRule] = []
    for r in all_rule_dicts:
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
