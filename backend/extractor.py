"""Rule extraction using Claude API — chunked by section.

Sends each document section to Claude individually with global context
and canonical field vocabulary, then merges, normalises, and de-duplicates.

Implements PRD F-05 through F-08c.
"""

import json
import os
import pathlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import anthropic

from schema import (
    ExtractedRule, ExtractionResult, GuardrailFlag,
    RuleCategory, RuleStatus, RuleScope,
)
from parser import ParsedDocument, ParsedSection

client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

MODEL = "claude-sonnet-4-6"

# ── Load canonical dictionary for field name constraints ──

CANONICAL_PATH = pathlib.Path(__file__).parent.parent / "canonical" / "dictionary.json"
try:
    with open(CANONICAL_PATH) as _f:
        CANONICAL_DICT = json.load(_f)
except FileNotFoundError:
    CANONICAL_DICT = {"fields": {}, "categories": {}}

# Build reverse lookup: canonical long-form → short key, plus key → key
_FIELD_REVERSE_MAP: dict[str, str] = {}
for _key, _meta in CANONICAL_DICT.get("fields", {}).items():
    _FIELD_REVERSE_MAP[_key] = _key
    _FIELD_REVERSE_MAP[_meta["canonical"]] = _key
    # Also map common variations (underscores to match)
    _FIELD_REVERSE_MAP[_meta["canonical"].replace("_", " ")] = _key


def _build_canonical_field_list() -> str:
    """Build a formatted reference of all canonical field names for the prompt."""
    fields = CANONICAL_DICT.get("fields", {})
    if not fields:
        return ""
    lines = [
        "## PREFERRED FIELD NAMES",
        "When a rule matches one of these fields, use the exact name below. For rules that do NOT match any listed field, create a descriptive snake_case name (e.g. deposit_source, residency_period).",
        "",
    ]
    # Group by category
    by_cat: dict[str, list[str]] = {}
    for key, meta in fields.items():
        cat = meta.get("category", "other")
        unit = meta.get("unit") or ""
        by_cat.setdefault(cat, []).append(f"  - {key} ({unit})" if unit else f"  - {key}")

    for cat in sorted(by_cat):
        lines.append(f"**{cat.upper()}:**")
        lines.extend(sorted(by_cat[cat]))
        lines.append("")

    lines.append("IMPORTANT: Still extract ALL rules even if no field name above matches. Use a descriptive snake_case name for any rule not covered above.")
    return "\n".join(lines)


CANONICAL_FIELDS_BLOCK = _build_canonical_field_list()

# ── Boilerplate section detection (shared with guardrails) ──

BOILERPLATE_HEADINGS_EXACT = {
    "table of contents", "contents", "version history", "change log",
    "document control", "disclaimer",
}

BOILERPLATE_HEADINGS_STARTSWITH = [
    "appendix",
]


def _is_boilerplate_section(heading: str) -> bool:
    lower = heading.lower().strip()
    if lower in BOILERPLATE_HEADINGS_EXACT:
        return True
    return any(lower.startswith(bp) for bp in BOILERPLATE_HEADINGS_STARTSWITH)


# ── Prompt template (trimmed for token efficiency) ──

SECTION_PROMPT = """You are a mortgage lending policy analyst extracting structured rules from lender criteria documents.

## TASK
Extract ALL lending rules from the section below. Every threshold, limit, condition, requirement, and eligibility criterion is a rule.

## GLOBAL CONTEXT
{global_context}

{canonical_fields}

## OUTPUT FORMAT
Return a JSON array. Each rule object must have these fields:
- **rule_id**: sequential ID (e.g. LTV_001, INC_001, EMP_001, CRD_001, PROP_001, AFF_001, APP_001, LOAN_001)
- **category**: one of: ltv, income, employment, credit, property, affordability, applicant, loan
- **field**: use a canonical field name from the list above when possible
- **operator**: one of: <=, >=, ==, IN, NOT IN, BETWEEN
- **value**: the threshold or allowed value(s)
- **unit**: %, £, years, months, x, or null
- **conditions**: qualifying context object or null
- **outcome**: PASS, REFER, or DECLINE
- **failure_outcome**: REFER or DECLINE
- **nl_statement**: clear English rule statement
- **source_quote**: EXACT VERBATIM text from the section (non-negotiable)
- **source_section**: section heading
- **source_page**: integer or null
- **condition_logic**: IF/THEN expression or null
- **precedence**: integer (1=lowest, higher overrides lower)
- **rule_scope**: "general" or "specific_exception"
- **overrides_rule_id**: rule_id of overridden general rule, or null
- **footnote_ref**: footnote text or null

## RULES
- Every rule MUST have a verbatim source_quote copied from the section
- Ambiguous language ("typically", "may", "case-by-case") → outcome: REFER, condition_logic: "MANUAL_LOGIC_REQUIRED: [phrase]"
- Table rows → separate rules unless clearly sub-conditions of one rule
- Footnotes (*,†) → capture in footnote_ref
- General vs exception: broadest rule = "general" (lower precedence), narrower = "specific_exception" (higher precedence, set overrides_rule_id)
- If no rules in this section, return: []

## SECTION: {section_heading}
{section_text}

Return ONLY the JSON array."""


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
    """Attempt to recover a valid JSON array from a truncated response."""
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

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
) -> list[dict]:
    """Extract rules from a single document section via Claude API."""
    section_text = section.text
    if section.tables:
        section_text += "\n\n" + "\n".join(section.tables)

    if len(section_text.strip()) < 50:
        return []

    heading = section.section_heading or "Untitled Section"

    prompt = SECTION_PROMPT.format(
        global_context=global_context,
        canonical_fields=CANONICAL_FIELDS_BLOCK,
        section_heading=heading,
        section_text=section_text,
    )

    raw_text = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
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

    for r in rules_data:
        if section.page is not None and not r.get("source_page"):
            r["source_page"] = section.page
        if not r.get("source_section"):
            r["source_section"] = heading

    return rules_data


def _normalise_fields(rule_dicts: list[dict]) -> list[dict]:
    """Normalise field names to canonical short forms using the dictionary."""
    for r in rule_dicts:
        field = r.get("field", "").lower().strip()
        if field in _FIELD_REVERSE_MAP:
            r["canonical_field"] = _FIELD_REVERSE_MAP[field]
            r["field"] = _FIELD_REVERSE_MAP[field]
        else:
            # Try fuzzy: strip common prefixes/suffixes
            stripped = field.replace("maximum_", "max_").replace("minimum_", "min_")
            if stripped in _FIELD_REVERSE_MAP:
                r["canonical_field"] = _FIELD_REVERSE_MAP[stripped]
                r["field"] = _FIELD_REVERSE_MAP[stripped]
            else:
                r["canonical_field"] = field
    return rule_dicts


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

    If parsed_doc is provided, uses chunked extraction (parallel across sections).
    Otherwise falls back to single-pass extraction on full_text.
    """
    global_context = _build_global_context(definitions or [])

    sections = parsed_doc.sections if parsed_doc else []

    # ── Chunked extraction: parallel across sections ──
    all_rule_dicts: list[dict] = []

    if sections:
        # Filter: skip tiny and boilerplate sections
        viable_sections = [
            s for s in sections
            if len((s.text + " ".join(s.tables if s.tables else [])).strip()) >= 50
            and not _is_boilerplate_section(s.section_heading or "")
        ]
        print(f"Extracting from {len(viable_sections)} sections (of {len(sections)} total, skipped {len(sections) - len(viable_sections)} boilerplate)...")

        max_workers = min(8, len(viable_sections))  # Up to 8 concurrent API calls

        def _extract_with_index(args):
            idx, section = args
            heading = section.section_heading or "Untitled"
            print(f"[{idx+1}/{len(viable_sections)}] Starting: {heading} ({section.char_count} chars)")
            try:
                rules = _extract_section(section, global_context)
                print(f"[{idx+1}/{len(viable_sections)}] Done: {heading} → {len(rules)} rules")
                return rules
            except Exception as e:
                print(f"[{idx+1}/{len(viable_sections)}] Failed: {heading} — {e}")
                return []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_extract_with_index, (i, s)): i
                for i, s in enumerate(viable_sections)
            }
            results_by_index: dict[int, list[dict]] = {}
            for future in as_completed(futures):
                idx = futures[future]
                results_by_index[idx] = future.result()

            for idx in sorted(results_by_index):
                all_rule_dicts.extend(results_by_index[idx])

        print(f"Total rules before de-duplication: {len(all_rule_dicts)}")
    else:
        # Fallback: single-pass extraction
        prompt = SECTION_PROMPT.format(
            global_context=global_context,
            canonical_fields=CANONICAL_FIELDS_BLOCK,
            section_heading="Full Document",
            section_text=full_text,
        )
        raw_text = ""
        with client.messages.stream(
            model=MODEL,
            max_tokens=16384,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                raw_text += text

        raw_text = _strip_json_fences(raw_text)
        raw_text = _repair_truncated_json(raw_text)
        all_rule_dicts = json.loads(raw_text)

    # ── Post-processing pipeline ──
    all_rule_dicts = _normalise_fields(all_rule_dicts)
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
        r.setdefault("canonical_field", None)

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
