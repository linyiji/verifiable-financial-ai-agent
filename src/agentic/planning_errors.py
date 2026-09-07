"""Bounded failure classification, without prompts, outputs or exception bodies."""

from enum import StrEnum


class PlanningFailureStage(StrEnum):
    PLANNING_INPUT_CONTRACT = "PLANNING_INPUT_CONTRACT"
    MODEL_INVOCATION = "MODEL_INVOCATION"
    STRUCTURED_OUTPUT_SCHEMA = "STRUCTURED_OUTPUT_SCHEMA"
    DECODER_PARSER = "DECODER_PARSER"
    DECISION_VALIDATION = "DECISION_VALIDATION"
    SCHEME_VALIDATION = "SCHEME_VALIDATION"


class IncrementalSchemeFailure(ValueError):
    def __init__(self, stage, *, provider_failure=None, attempted_count=0):
        from src.adapters.llm.provider import LLMFailureClassification

        self.stage = PlanningFailureStage(stage)
        self.provider_failure = (
            LLMFailureClassification(provider_failure) if provider_failure is not None else None
        )
        self.attempted_count = attempted_count
        self.reason_code = "INCREMENTAL_" + self.stage.value
        if self.provider_failure:
            self.reason_code += "_" + self.provider_failure.value.upper()
        super().__init__(self.reason_code)
