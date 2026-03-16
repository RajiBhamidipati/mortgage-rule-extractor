"""Pydantic models for the Mortgage Policy Rule Extractor.

Covers all four entity groups from PRD Section 7:
- Entity Group 1: Policy and Rules Layer (ExtractedRule)
- Entity Group 4: Governance Layer (ReviewAction)
- Evaluation models (EvalReport)
"""

from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional
from datetime import datetime


# ── Enums ──

class RuleCategory(str, Enum):
    LTV = "ltv"
    INCOME = "income"
    EMPLOYMENT = "employment"
    CREDIT = "credit"
    PROPERTY = "property"
    AFFORDABILITY = "affordability"
    APPLICANT = "applicant"
    LOAN = "loan"


class RuleStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FLAGGED_REGULATORY = "flagged_regulatory"
    FLAGGED_UNCERTAIN = "flagged_uncertain"


class Operator(str, Enum):
    LTE = "<="
    GTE = ">="
    EQ = "=="
    IN = "IN"
    NOT_IN = "NOT IN"
    BETWEEN = "BETWEEN"


class Outcome(str, Enum):
    PASS = "PASS"
    REFER = "REFER"
    DECLINE = "DECLINE"


class RuleScope(str, Enum):
    GENERAL = "general"
    SPECIFIC_EXCEPTION = "specific_exception"


# ── Guardrail Flag ──

class GuardrailFlag(BaseModel):
    type: str  # e.g. HALLUCINATION, COMPLETENESS, MISCLASSIFIED_CANDIDATE, REGULATORY_BIAS, MANUAL_LOGIC_REQUIRED, UNMAPPED_TERM
    reason: str  # Human-readable explanation (F-13)


# ── Entity Group 1: Extracted Rule ──

class ExtractedRule(BaseModel):
    """Single extracted lending rule — PRD Section 7.1."""
    rule_id: str = Field(description="Unique rule identifier, e.g. LTV_001")
    policy_doc_id: str = Field(description="Reference to source document")
    version: str = Field(default="1.0")
    effective_date: Optional[str] = Field(default=None, description="Date rule becomes active")
    category: RuleCategory
    field: str = Field(description="Application data field this rule evaluates, e.g. max_ltv")
    operator: str = Field(description="Comparison operator: <=, >=, ==, IN, NOT IN, BETWEEN")
    value: str = Field(description="Threshold or permitted value set")
    unit: Optional[str] = Field(default=None, description="%, £, years, etc.")
    conditions: Optional[dict] = Field(default=None, description="Qualifying context: property_type, applicant_type, etc.")
    outcome: str = Field(description="PASS, REFER, or DECLINE")
    failure_outcome: Optional[str] = Field(default=None, description="REFER or DECLINE when rule fails")
    nl_statement: str = Field(description="Human-readable rule statement")
    source_quote: str = Field(description="Verbatim text from source document")
    source_section: Optional[str] = Field(default=None, description="Section reference")
    source_page: Optional[int] = Field(default=None, description="Page number in source document")
    doc_name: str = Field(description="Source filename")
    condition_logic: Optional[str] = Field(default=None, description="Full IF statement, e.g. IF property_type == 'HMO' THEN max_ltv = 75%")
    precedence: Optional[int] = Field(default=None, description="Rule priority — higher values override lower")
    rule_scope: Optional[RuleScope] = Field(default=RuleScope.GENERAL, description="general or specific_exception")
    overrides_rule_id: Optional[str] = Field(default=None, description="Rule ID this overrides, if specific_exception")
    footnote_ref: Optional[str] = Field(default=None, description="Footnote reference modifying this rule")
    canonical_field: Optional[str] = Field(default=None, description="Normalised field name from canonical dictionary")
    canonical_category: Optional[str] = Field(default=None, description="Normalised category from canonical taxonomy")
    status: RuleStatus = Field(default=RuleStatus.PENDING_REVIEW)
    guardrail_flags: list[GuardrailFlag] = Field(default_factory=list)
    reviewed_by: Optional[str] = Field(default=None)
    reviewed_at: Optional[datetime] = Field(default=None)


# ── Extraction Result ──

class ExtractionResult(BaseModel):
    """Output of a single extraction run."""
    rules: list[ExtractedRule]
    doc_name: str
    doc_id: str
    extraction_timestamp: str
    model_used: str
    total_rules_extracted: int
    sections_processed: list[str] = Field(default_factory=list)
    sections_with_no_rules: list[str] = Field(default_factory=list)


# ── Review Action (Governance Layer) ──

class ReviewAction(BaseModel):
    """Audit trail entry for a reviewer action — PRD Section 7.4."""
    rule_id: str
    action: str  # accept, reject, edit_accept, flag_regulatory, flag_uncertain
    reviewed_by: str
    reviewed_at: datetime
    previous_status: RuleStatus
    new_status: RuleStatus
    edits: Optional[dict] = Field(default=None, description="Fields that were edited")
    comments: Optional[str] = None


# ── Rule Update Request ──

class RuleUpdateRequest(BaseModel):
    """Request body for PATCH /api/rules/{doc_id}/{rule_id}."""
    status: Optional[RuleStatus] = None
    reviewed_by: Optional[str] = None
    edits: Optional[dict] = None
    comments: Optional[str] = None


# ── Eval Report ──

class EvalReport(BaseModel):
    """Evaluation metrics per extraction run — PRD Section 6.5."""
    timestamp: str
    doc_id: str
    doc_name: str
    precision: float
    recall: float
    f1: float
    source_fidelity: float
    classification_accuracy: float
    eqs: float  # Extraction Quality Score (0-100)
    rag_status: str  # green, amber, red
    total_extracted: int
    total_golden: int
    true_positives: int
    false_positives: int
    false_negatives: int
    missed_rules: list[str] = Field(default_factory=list)
    extra_rules: list[str] = Field(default_factory=list)
    human_adjustments: int = Field(default=0, description="Rules accepted/rejected by reviewer")


# ── Session State ──

class SessionState(BaseModel):
    """In-memory session for a single document processing run."""
    doc_id: str
    doc_name: str
    doc_type: str
    upload_timestamp: str
    parsed_text: str = ""
    sections: list[dict] = Field(default_factory=list)
    rules: list[ExtractedRule] = Field(default_factory=list)
    completeness_warnings: list[str] = Field(default_factory=list)
    review_log: list[ReviewAction] = Field(default_factory=list)
    eval_report: Optional[EvalReport] = None
    extraction_done: bool = False
    guardrails_done: bool = False
