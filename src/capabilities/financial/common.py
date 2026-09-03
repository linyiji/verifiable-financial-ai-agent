from decimal import Decimal
from typing import Any

from src.domain.enums import EvidenceStatus
from src.domain.evidence import EvidenceRecord


class FinancialCapabilityError(ValueError):
    pass


class MissingEvidenceError(FinancialCapabilityError):
    pass


class UnacceptedEvidenceError(FinancialCapabilityError):
    pass


class PeriodMismatchError(FinancialCapabilityError):
    pass


class ZeroDenominatorError(FinancialCapabilityError):
    pass


def require_accepted(record: EvidenceRecord) -> EvidenceRecord:
    if record.status is not EvidenceStatus.ACCEPTED:
        raise UnacceptedEvidenceError(
            f"evidence {record.evidence_id} has status {record.status.value}, expected ACCEPTED"
        )
    return record


def decimal_value(value: Any) -> Decimal:
    if value is None:
        raise MissingEvidenceError("evidence value is missing")
    try:
        return Decimal(str(value))
    except Exception as exc:  # pragma: no cover - Decimal reports several concrete errors
        raise FinancialCapabilityError(f"value is not numeric: {value!r}") from exc
