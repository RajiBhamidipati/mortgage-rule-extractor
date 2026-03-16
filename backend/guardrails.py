"""Four guardrail checks for extracted rules.

Implements PRD F-09 through F-13:
1. Hallucination check — verify source_quote exists in document
2. Completeness check — flag sections with low rule density
3. Classification validator — second Claude pass to verify categories
4. Regulatory bias check — flag protected characteristics and FCA MCOB concerns
5. Footnote check — link footnotes to rules (F-12b)

Every flag includes a human-readable reason (F-13).
"""

import json
import os
import re

import anthropic

from schema import ExtractedRule, GuardrailFlag, RuleStatus
from parser import ParsedDocument

client = anthropic.Anthropic()
MODEL = "claude-sonnet-4-6"


# ── Guardrail 1: Hallucination Check (F-09) ──

def check_hallucination(rules: list[ExtractedRule], parsed_doc: ParsedDocument) -> list[ExtractedRule]:
    """Verify each rule's source_quote exists verbatim in the document text."""
    doc_text = parsed_doc.full_text

    for rule in rules:
        if not rule.source_quote:
            rule.guardrail_flags.append(GuardrailFlag(
                type="HALLUCINATION",
                reason="No source_quote provided for this rule",
            ))
            continue

        # Exact match first
        if rule.source_quote in doc_text:
            continue

        # Normalised match: collapse whitespace and lowercase
        norm_quote = " ".join(rule.source_quote.lower().split())
        norm_doc = " ".join(doc_text.lower().split())

        if norm_quote in norm_doc:
            continue

        # Substring match: try with first 60 chars (PDF extraction can truncate)
        short_quote = norm_quote[:60]
        if len(short_quote) > 20 and short_quote in norm_doc:
            continue

        # Flag as hallucination
        rule.guardrail_flags.append(GuardrailFlag(
            type="HALLUCINATION",
            reason=f"source_quote not found in document text. Quote starts: '{rule.source_quote[:80]}...'",
        ))

    return rules


# ── Guardrail 2: Completeness Check (F-10) ──

def check_completeness(
    rules: list[ExtractedRule],
    parsed_doc: ParsedDocument,
) -> tuple[list[ExtractedRule], list[str]]:
    """Flag sections with unexpectedly low rule density."""
    warnings: list[str] = []

    # Build map of sections → rule count
    section_rule_counts: dict[str, int] = {}
    for section in parsed_doc.sections:
        heading = section.section_heading
        if not heading:
            continue

        count = sum(
            1 for r in rules
            if r.source_section and _sections_match(r.source_section, heading)
        )
        section_rule_counts[heading] = count

        # Heuristic: sections with substantial text but zero rules are suspicious
        # Skip intro/appendix sections
        if (
            section.char_count > 200
            and count == 0
            and not _is_boilerplate_section(heading)
        ):
            warnings.append(
                f"COMPLETENESS: Section '{heading}' has {section.char_count} chars "
                f"but 0 extracted rules — may require manual review"
            )

    return rules, warnings


def _sections_match(rule_section: str, doc_section: str) -> bool:
    """Fuzzy match between rule's source_section and document section heading."""
    r = rule_section.lower().strip()
    d = doc_section.lower().strip()
    # Exact or substring match
    return r == d or r in d or d in r


def _is_boilerplate_section(heading: str) -> bool:
    """Sections that typically don't contain extractable rules."""
    boilerplate = [
        "table of contents", "contents", "introduction", "appendix",
        "definitions", "glossary", "version history", "change log",
        "document control", "disclaimer",
    ]
    lower = heading.lower()
    return any(bp in lower for bp in boilerplate)


# ── Guardrail 3: Classification Validator (F-11) ──

def check_classification(rules: list[ExtractedRule]) -> list[ExtractedRule]:
    """Second-pass Claude call to verify category/field assignments."""
    if not rules:
        return rules

    # Build compact summaries for validation
    rule_summaries = [
        {
            "rule_id": r.rule_id,
            "category": r.category.value if hasattr(r.category, "value") else r.category,
            "field": r.field,
            "nl_statement": r.nl_statement,
        }
        for r in rules
    ]

    validation_prompt = f"""You are a mortgage lending classification auditor. Review each rule's category assignment.

Valid categories: ltv, income, employment, credit, property, affordability, applicant, loan

For each rule, confirm if the category is correct based on the nl_statement.

Rules to validate:
{json.dumps(rule_summaries, indent=2)}

Return a JSON array of objects with:
- rule_id: string
- original_category: string
- is_correct: boolean
- suggested_category: string (only if is_correct is false)
- reason: string (only if is_correct is false)

Return ONLY the JSON array."""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": validation_prompt}],
        )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

        validations = json.loads(raw.strip())

        rule_map = {r.rule_id: r for r in rules}
        for v in validations:
            if not v.get("is_correct", True):
                rule = rule_map.get(v["rule_id"])
                if rule:
                    rule.guardrail_flags.append(GuardrailFlag(
                        type="MISCLASSIFIED_CANDIDATE",
                        reason=(
                            f"Category '{v.get('original_category')}' may be "
                            f"'{v.get('suggested_category')}': {v.get('reason', 'no reason given')}"
                        ),
                    ))

    except Exception as e:
        print(f"Warning: classification validator failed: {e}")

    return rules


# ── Guardrail 4: Regulatory Bias Check (F-12) ──

PROTECTED_CHARACTERISTICS = [
    "age", "gender", "sex", "race", "ethnicity", "religion",
    "disability", "marital status", "pregnancy", "sexual orientation",
    "nationality", "national origin", "marriage", "civil partnership",
]

FCA_MCOB_CONCERNS = [
    "treating customers fairly", "tcf", "conduct risk",
    "vulnerable customer", "affordability assessment",
    "automatic decline", "blanket decline",
]

# Terms that LOOK like protected characteristics but are legitimate lending criteria
LEGITIMATE_LENDING_TERMS = {
    "age": ["maximum age at end of mortgage term", "minimum age at the time of application",
            "minimum age", "maximum age", "age at application", "age at end of term"],
}


def check_regulatory(rules: list[ExtractedRule]) -> list[ExtractedRule]:
    """Flag rules referencing protected characteristics or FCA MCOB concerns."""
    for rule in rules:
        combined = " ".join([
            rule.nl_statement or "",
            rule.field or "",
            json.dumps(rule.conditions) if rule.conditions else "",
            rule.source_quote or "",
        ]).lower()

        # Check protected characteristics
        for char in PROTECTED_CHARACTERISTICS:
            if char in combined:
                # Check if it's a legitimate lending term (e.g. "age" in max-age-at-term rules)
                is_legitimate = False
                if char in LEGITIMATE_LENDING_TERMS:
                    for legit in LEGITIMATE_LENDING_TERMS[char]:
                        if legit in combined:
                            is_legitimate = True
                            break

                flag_type = "REGULATORY_BIAS"
                reason = (
                    f"References protected characteristic '{char}'. "
                )
                if is_legitimate:
                    reason += "This appears to be a standard lending criterion but requires compliance review."
                else:
                    reason += "Requires FCA MCOB review to confirm this is not discriminatory."
                    rule.status = RuleStatus.FLAGGED_REGULATORY

                rule.guardrail_flags.append(GuardrailFlag(type=flag_type, reason=reason))

        # Check FCA MCOB concern keywords
        for keyword in FCA_MCOB_CONCERNS:
            if keyword in combined:
                rule.guardrail_flags.append(GuardrailFlag(
                    type="FCA_MCOB_CONCERN",
                    reason=f"FCA MCOB keyword detected: '{keyword}'. Requires compliance review.",
                ))

    return rules


# ── Guardrail 5: Footnote Check (F-12b) ──

def check_footnotes(rules: list[ExtractedRule], parsed_doc: ParsedDocument) -> list[ExtractedRule]:
    """Link footnotes to rules they modify."""
    doc_text = parsed_doc.full_text

    # Find footnote-like patterns in the document
    footnote_pattern = re.compile(r'[*†‡§]\s+(.{10,100})')
    footnotes = footnote_pattern.findall(doc_text)

    # Also find numeric footnotes like "1. Some footnote text"
    numeric_footnote_pattern = re.compile(r'^\d+[.)]\s+(.{10,100})', re.MULTILINE)
    footnotes.extend(numeric_footnote_pattern.findall(doc_text))

    # For rules that already have footnote_ref from extraction, verify the footnote exists
    for rule in rules:
        if rule.footnote_ref:
            # Try to find the footnote text in the document
            found = any(rule.footnote_ref.strip("* ") in fn for fn in footnotes)
            if not found and footnotes:
                rule.guardrail_flags.append(GuardrailFlag(
                    type="FOOTNOTE_UNVERIFIED",
                    reason=f"Footnote reference '{rule.footnote_ref}' could not be verified in document text",
                ))

    return rules


# ── Run All Guardrails ──

def run_all_guardrails(
    rules: list[ExtractedRule],
    parsed_doc: ParsedDocument,
) -> tuple[list[ExtractedRule], list[str]]:
    """Execute all guardrail checks in sequence.

    Returns:
        Tuple of (rules with flags, completeness warnings)
    """
    # 1. Hallucination
    rules = check_hallucination(rules, parsed_doc)

    # 2. Completeness
    rules, completeness_warnings = check_completeness(rules, parsed_doc)

    # 3. Classification (requires API call)
    rules = check_classification(rules)

    # 4. Regulatory bias
    rules = check_regulatory(rules)

    # 5. Footnotes
    rules = check_footnotes(rules, parsed_doc)

    return rules, completeness_warnings
