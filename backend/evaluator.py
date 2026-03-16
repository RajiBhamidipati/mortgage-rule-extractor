"""Evaluation metrics: precision, recall, F1, source fidelity, EQS.

Implements PRD F-20 through F-23.
Compares extracted rules against a golden dataset to produce
automated scoring and a JSON eval report.
"""

import json
import os
import pathlib
from datetime import datetime, timezone

from schema import ExtractedRule, EvalReport

# Load canonical dictionary for field normalisation during eval matching
_CANONICAL_PATH = pathlib.Path(__file__).parent.parent / "canonical" / "dictionary.json"
try:
    with open(_CANONICAL_PATH) as _f:
        _CANONICAL_DICT = json.load(_f)
except FileNotFoundError:
    _CANONICAL_DICT = {"fields": {}}

# Build reverse map: canonical long-form and common variations → short key
_FIELD_NORM: dict[str, str] = {}
for _key, _meta in _CANONICAL_DICT.get("fields", {}).items():
    _FIELD_NORM[_key] = _key
    _FIELD_NORM[_meta["canonical"]] = _key


def _normalise_field(field: str) -> str:
    """Normalise a field name to its canonical short form."""
    f = field.lower().strip()
    if f in _FIELD_NORM:
        return _FIELD_NORM[f]
    # Try common prefix substitutions
    stripped = f.replace("maximum_", "max_").replace("minimum_", "min_")
    if stripped in _FIELD_NORM:
        return _FIELD_NORM[stripped]
    return f


def _match_key(rule: dict | ExtractedRule) -> tuple[str, str]:
    """Create a matching key from (category, normalised field) for rule comparison."""
    if isinstance(rule, dict):
        return (rule.get("category", "").lower(), _normalise_field(rule.get("field", "")))
    cat = rule.category.value if hasattr(rule.category, "value") else str(rule.category)
    return (cat.lower(), _normalise_field(rule.field))


def compute_precision_recall(
    extracted: list[ExtractedRule],
    golden: list[dict],
) -> dict:
    """Match extracted rules to golden rules by (category, field) pair."""
    golden_keys = {_match_key(g) for g in golden}
    extracted_keys = {_match_key(e) for e in extracted}

    true_positives = golden_keys & extracted_keys
    false_positives = extracted_keys - golden_keys
    false_negatives = golden_keys - extracted_keys

    precision = len(true_positives) / len(extracted_keys) if extracted_keys else 0
    recall = len(true_positives) / len(golden_keys) if golden_keys else 0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positives": len(true_positives),
        "false_positives": len(false_positives),
        "false_negatives": len(false_negatives),
        "missed_rules": [f"{k[0]}:{k[1]}" for k in sorted(false_negatives)],
        "extra_rules": [f"{k[0]}:{k[1]}" for k in sorted(false_positives)],
    }


def compute_source_fidelity(extracted: list[ExtractedRule], doc_text: str) -> float:
    """Percentage of rules whose source_quote appears in the document."""
    if not extracted:
        return 0.0
    matched = 0
    norm_doc = " ".join(doc_text.lower().split())
    for e in extracted:
        if not e.source_quote:
            continue
        norm_quote = " ".join(e.source_quote.lower().split())
        if norm_quote in norm_doc or norm_quote[:60] in norm_doc:
            matched += 1
    return round(matched / len(extracted), 4)


def compute_classification_accuracy(
    extracted: list[ExtractedRule],
    golden: list[dict],
) -> float:
    """For matched rules, percentage with correct category."""
    golden_map = {_match_key(g): g.get("category", "").lower() for g in golden}
    matched = 0
    correct = 0
    for e in extracted:
        key = _match_key(e)
        if key in golden_map:
            matched += 1
            cat = e.category.value if hasattr(e.category, "value") else str(e.category)
            if cat.lower() == golden_map[key]:
                correct += 1
    return round(correct / matched, 4) if matched else 0.0


def compute_eqs(precision: float, recall: float, classification: float, source_fidelity: float) -> float:
    """Extraction Quality Score — weighted composite (0-100).

    Weights from PRD Section 12:
    - Precision: 30%
    - Recall: 30%
    - Classification accuracy: 25%
    - Source fidelity: 15%
    """
    eqs = (
        0.30 * precision
        + 0.30 * recall
        + 0.25 * classification
        + 0.15 * source_fidelity
    )
    return round(eqs * 100, 1)


def rag_status(eqs: float) -> str:
    """RAG status: green ≥85, amber 70-84, red <70."""
    if eqs >= 85:
        return "green"
    elif eqs >= 70:
        return "amber"
    else:
        return "red"


def run_evaluation(
    extracted_rules: list[ExtractedRule],
    golden_path: str,
    doc_text: str,
    doc_id: str,
    doc_name: str,
) -> EvalReport:
    """Run full evaluation and save JSON report.

    Args:
        extracted_rules: Rules from the extraction pipeline
        golden_path: Path to golden_dataset.json
        doc_text: Full document text for source fidelity check
        doc_id: Document identifier
        doc_name: Document filename

    Returns:
        EvalReport with all metrics
    """
    with open(golden_path) as f:
        golden = json.load(f)

    pr = compute_precision_recall(extracted_rules, golden)
    sf = compute_source_fidelity(extracted_rules, doc_text)
    ca = compute_classification_accuracy(extracted_rules, golden)
    eqs = compute_eqs(pr["precision"], pr["recall"], ca, sf)
    status = rag_status(eqs)

    # Count human adjustments (approved or rejected rules)
    human_adj = sum(
        1 for r in extracted_rules
        if r.status.value in ("approved", "rejected")
    )

    report = EvalReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        doc_id=doc_id,
        doc_name=doc_name,
        precision=pr["precision"],
        recall=pr["recall"],
        f1=pr["f1"],
        source_fidelity=sf,
        classification_accuracy=ca,
        eqs=eqs,
        rag_status=status,
        total_extracted=len(extracted_rules),
        total_golden=len(golden),
        true_positives=pr["true_positives"],
        false_positives=pr["false_positives"],
        false_negatives=pr["false_negatives"],
        missed_rules=pr["missed_rules"],
        extra_rules=pr["extra_rules"],
        human_adjustments=human_adj,
    )

    # Save report to evals/eval_reports/
    report_dir = os.path.join(os.path.dirname(__file__), "..", "evals", "eval_reports")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(
        report_dir,
        f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{doc_id}.json",
    )
    with open(report_path, "w") as f:
        json.dump(report.model_dump(), f, indent=2, default=str)

    return report
