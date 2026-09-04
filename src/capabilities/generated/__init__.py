"""Governed generated-capability orchestration boundaries.

The package deliberately excludes static analysis, sandbox execution, financial
validation, and scoped-registry implementations.  Those are injected through
ports so generated source never becomes executable merely because an LLM
returned it.
"""

from src.capabilities.generated.builder import TeamoRouterCodeBuilder
from src.capabilities.generated.models import (
    CapabilityBuildRequest,
    CapabilityOrchestrationResult,
    CodeBuilderOutput,
    GeneratedCapabilityCandidate,
    ResearchLeadCapabilityApproval,
    SpecialistCapabilityRequest,
    ValidationHandoff,
)
from src.capabilities.generated.orchestration import (
    CapabilityBuildFailedError,
    GeneratedCapabilityOrchestrator,
)
from src.capabilities.generated.ports import (
    CapabilityWorkflowRecorder,
    CodeBuilder,
    GeneratedCapabilityValidationPort,
    ResearchLeadCapabilityAuthority,
    ScopedCapabilityRegistryPort,
)
from src.capabilities.generated.scoped_registry import ScopedCapabilityRegistry
from src.capabilities.generated.telemetry import GeneratedCapabilityTrace
from src.capabilities.generated.validation import (
    CallableFinancialValidationPolicy,
    CapabilityValidationPlan,
    GeneratedCapabilityExecutionError,
    GeneratedCapabilityValidationError,
    GeneratedCapabilityValidator,
    SandboxValidatedGeneratedCapability,
    StaticCapabilityValidationPlanProvider,
)

__all__ = [
    "CapabilityBuildFailedError",
    "CapabilityBuildRequest",
    "CapabilityOrchestrationResult",
    "CapabilityWorkflowRecorder",
    "CapabilityValidationPlan",
    "CallableFinancialValidationPolicy",
    "CodeBuilder",
    "CodeBuilderOutput",
    "GeneratedCapabilityCandidate",
    "GeneratedCapabilityExecutionError",
    "GeneratedCapabilityOrchestrator",
    "GeneratedCapabilityTrace",
    "GeneratedCapabilityValidationError",
    "GeneratedCapabilityValidator",
    "GeneratedCapabilityValidationPort",
    "ResearchLeadCapabilityApproval",
    "ResearchLeadCapabilityAuthority",
    "SandboxValidatedGeneratedCapability",
    "ScopedCapabilityRegistry",
    "ScopedCapabilityRegistryPort",
    "SpecialistCapabilityRequest",
    "StaticCapabilityValidationPlanProvider",
    "TeamoRouterCodeBuilder",
    "ValidationHandoff",
]
