from enum import StrEnum


class RunStatus(StrEnum):
    DRAFT = "DRAFT"
    SCHEME_GENERATING = "SCHEME_GENERATING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    REVIEW = "REVIEW"
    PROVING = "PROVING"
    RELEASED = "RELEASED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskStatus(StrEnum):
    CREATED = "CREATED"
    WAITING = "WAITING"
    READY = "READY"
    RUNNING = "RUNNING"
    SELF_CORRECTING = "SELF_CORRECTING"
    BLOCKED = "BLOCKED"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskOrigin(StrEnum):
    PLAN = "PLAN"
    REPLAN = "REPLAN"
    REVIEW_FIX = "REVIEW_FIX"


class CapabilityBackend(StrEnum):
    NATIVE = "NATIVE"
    MCP = "MCP"
    GENERATED = "GENERATED"


class EvidenceStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"
    PARTIAL = "PARTIAL"


class ReviewStatus(StrEnum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class ProofStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


class CalculationStatus(StrEnum):
    PASS = "PASS"
    FAILED = "FAILED"


class ReplanDecision(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CorrectionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"

