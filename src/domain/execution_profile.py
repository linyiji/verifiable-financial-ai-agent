"""Versioned product permission values, carried by the existing node binding.

These are snapshots, not a registry or an alternative policy engine. Authority is
acquired only through the existing Confirm / frozen graph / admission transaction.
"""

from datetime import date
from typing import Literal

from pydantic import Field, model_serializer, model_validator

from src.data.capability_policy import FUNDAMENTALS_DATA_PERMISSION_VERSION, DataCapabilityPolicy
from src.domain.node_binding import BindingDenied, BindingValue, digest
from src.domain.owner_policy import OwnerTaskPolicy
from src.domain.recovery import RecoveryBudget, RouteId


class DataPermission(BindingValue):
    data_scope_id: Literal["COMPANY", "PEER", "RESEARCH_NEWS"]
    capability_id: str
    fields: tuple[str, ...] = ()
    observation_limit: int = Field(ge=1, le=500)
    expected_period: str | None = None
    category: str
    purpose: str
    providers: tuple[str, ...] = ("fmp",)
    max_requests: int = Field(default=6, ge=1)
    request_count_unit: Literal["CAPABILITY_INVOCATION"] = "CAPABILITY_INVOCATION"
    envelope_source: Literal["PROFILE_DEFAULT"] = "PROFILE_DEFAULT"
    requirement: Literal["ALLOWED_COLLECTOR_OWNS_REQUIREMENT"] = (
        "ALLOWED_COLLECTOR_OWNS_REQUIREMENT"
    )
    discovery_policy: DataCapabilityPolicy | None = None


REPORT_METRIC_MARKER = "frozen_report_metric_requirements/v1"
REPORT_METRIC_SCHEMA = "frozen-report-metric-requirements/v1"


class ReportMetricExpectation(BindingValue):
    metric_id: str
    capability_id: str
    capability_version: str
    implementation_hash: str
    object_id: str
    period: str = Field(pattern=r"^FY\d{4}$")
    prior_period: str | None = None
    as_of: date
    unit: Literal["ratio"] = "ratio"
    period_basis: Literal["FY"] = "FY"
    actuality: Literal["ACTUAL"] = "ACTUAL"


class ConditionalReportMetric(BindingValue):
    condition_ref: str
    metric_id: str
    resolved_enabled: bool = Field(strict=True)
    requirement_ref: str


class FrozenReportMetricRequirementsV1(BindingValue):
    schema_version: Literal["frozen-report-metric-requirements/v1"] = REPORT_METRIC_SCHEMA
    report_mode: Literal["METRIC_FOCUSED"] = "METRIC_FOCUSED"
    resolved_required_metric_ids: tuple[str, ...]
    optional_metric_ids: tuple[str, ...] = ()
    conditional_requirement_provenance: tuple[ConditionalReportMetric, ...] = ()
    metric_expectations: tuple[ReportMetricExpectation, ...]
    request_digest: str
    contract_digest: str

    @model_validator(mode="after")
    def validate_contract(self):
        required = self.resolved_required_metric_ids
        optional = self.optional_metric_ids
        expectations = self.metric_expectations
        provenance = self.conditional_requirement_provenance
        if (required != tuple(sorted(set(required)))
                or optional != tuple(sorted(set(optional)))
                or set(required) & set(optional)
                or not required
                or len({e.metric_id for e in expectations}) != len(expectations)
                or {e.metric_id for e in expectations} != set(required) | set(optional)
                    | {p.metric_id for p in provenance}
                or any(p.resolved_enabled and p.metric_id not in required for p in provenance)
                or digest(self.model_dump(exclude={"contract_digest"}), REPORT_METRIC_SCHEMA)
                != self.contract_digest):
            raise ValueError("Invalid frozen report metric requirements")
        return self


def report_metric_value(requirements, payload):
    markers = [r for r in requirements if r.startswith("frozen_report_metric_requirements/")]
    if not markers and payload is None:
        return None
    if markers != [REPORT_METRIC_MARKER] or payload is None:
        raise BindingDenied("CONTRACT_REJECTED", "report metric marker/value")
    try:
        return FrozenReportMetricRequirementsV1.model_validate(
            payload.model_dump()
            if isinstance(payload, FrozenReportMetricRequirementsV1) else payload
        )
    except (TypeError, ValueError) as exc:
        raise BindingDenied("CONTRACT_REJECTED", "report metric contract") from exc


class ScenarioProfile(BindingValue):
    scenario_id: str = "company_fundamental_research_v1"
    scenario_version: str = "1"
    permission_source: Literal["PRODUCT_DEFINED"] = "PRODUCT_DEFINED"
    research_depth: Literal["STANDARD_QUALITATIVE"] = "STANDARD_QUALITATIVE"
    task_categories: tuple[str, ...]
    evidence_requirement: str = "ACCEPTED_PROVENANCE_PERIOD_UNIT_AS_OF"
    counter_evidence_requirement: str = "CURRENT_RISK_NEWS_OUTPUT_AND_EXPLICIT_LIMITATIONS"
    valuation_requirement: Literal["NOT_QUANTIFIED_IN_CURRENT_SCOPE"] = (
        "NOT_QUANTIFIED_IN_CURRENT_SCOPE"
    )
    review_requirement: str = "INDEPENDENT_FINANCIAL_REVIEW_AND_EXISTING_RELEASE_GATES"
    report_requirements: tuple[str, ...] = ()
    report_metric_requirements: FrozenReportMetricRequirementsV1 | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    budget_policy: Literal["WIDE_NODE_LEVEL_ENVELOPES_V1"] = "WIDE_NODE_LEVEL_ENVELOPES_V1"
    aggregate_numeric_ceiling: Literal["NOT_YET_ENFORCED_IN_V1"] = "NOT_YET_ENFORCED_IN_V1"
    execution_family: str = "company_fundamental_nodes"
    execution_family_version: str = "1"
    stop_conditions: tuple[str, ...] = (
        "MISSING_HARD_INPUT",
        "IDENTITY_FAILURE",
        "INVALID_OUTPUT",
        "POLICY_DENIED",
        "NODE_ENVELOPE_EXHAUSTED",
        "REQUIRED_REVIEW_UNRESOLVED",
    )
    user_problem_expression: Literal["FREE"] = "FREE"
    clarity_and_planning: Literal["BOUNDED"] = "BOUNDED"
    graph_mutation: Literal["DISABLED", "RISK_ADD_CHILD_TASK_HUMAN_V1"] = "DISABLED"
    arbitrary_capability_discovery: Literal["DISABLED"] = "DISABLED"
    generated_methods_tools: Literal["DISABLED"] = "DISABLED"
    autonomous_replan: Literal["DISABLED"] = "DISABLED"
    report_schema: Literal["FIXED"] = "FIXED"
    core_formulas: Literal["FIXED"] = "FIXED"
    risk_semantic_contract: dict | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    risk_follow_up_policy: dict | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def validate_risk_replan_policy(self):
        report_metric_value(self.report_requirements, self.report_metric_requirements)
        if self.risk_semantic_contract is not None:
            from src.domain.risk_admission import validate_contract

            validate_contract(self.risk_semantic_contract)
        if self.risk_follow_up_policy is not None:
            from src.domain.risk_replan import POLICY, RiskFollowUpPolicyV1

            policy = RiskFollowUpPolicyV1.model_validate(self.risk_follow_up_policy)
            if (self.scenario_version != "2" or self.execution_family_version != "2"
                    or self.graph_mutation != POLICY
                    or policy.child_template_digest != digest(
                        policy.child_template, "node-execution-profile/v1")):
                raise ValueError("Corrupt Risk Replan policy")
        elif self.graph_mutation != "DISABLED":
            raise ValueError("Missing Risk Replan policy")
        return self


class AcceptedRequestProof(BindingValue):
    """Owner-adopted bounded evidence, frozen at Confirm; never a Run result."""

    adoption_version: str
    profile_version: str
    task_type: str
    skill_id: str
    agent_id: str
    provider: str
    route: RouteId
    model: str
    schema_name: str
    schema_identity: str
    schema_digest: str
    request_builder: str
    builder_digest: str
    template_digest: str
    valuation_context_enabled: bool | None
    workload_type: str
    status: str
    receipt_id: str
    attempt_id: str
    receipt_content_digest: str
    request_receipt_digest: str
    acceptance_digest: str

    # Absent extensions preserve historical proof bytes and acceptance identities.
    d01_identity: dict | None = Field(default=None, exclude_if=lambda value: value is None)
    d01_evidence: dict | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def validate_d01_identity(self):
        if self.d01_identity is None and self.d01_evidence is None:
            return self
        from src.phase4_product.hashing import canonical_json_sha256

        if self.d01_identity is None or self.d01_evidence is None:
            raise ValueError("Incomplete D01 proof evidence")
        family = self.d01_identity["family"]
        fields = {
            "execution_profile_version": "profile_version", "workload": "workload_type",
            **{key: key for key in (
                "task_type", "skill_id", "agent_id", "provider", "route", "model",
                "schema_name", "schema_identity", "schema_digest", "builder_digest",
                "template_digest",
            )},
        }
        if (any(family[key] != getattr(self, field) for key, field in fields.items())
                or canonical_json_sha256(family) != self.d01_identity["family_digest"]
                or family["response_format_digest"] != self.d01_identity["response_format_digest"]
                or (self.acceptance_digest and self.acceptance_digest != self.content_digest())):
            raise ValueError("Corrupt D01 accepted request proof")
        return self

    def content_digest(self):
        return digest(
            self.model_dump(exclude={"acceptance_digest"}), "accepted-request-proof/v1"
        )


class NodeExecutionProfile(BindingValue):
    profile_id: str
    profile_version: str = "1"
    task_type: str
    permission_source: Literal["PRODUCT_DEFINED"] = "PRODUCT_DEFINED"
    policy_evidence_source: str = "CURRENT_ACTIVE_OWNER_TASK_POLICY"
    execution_class: Literal["DETERMINISTIC", "BOUNDED_ADAPTIVE"]
    allowed_method_ids: tuple[str, ...]
    allowed_tool_ids: tuple[str, ...]
    data_scope_ids: tuple[str, ...] = ()
    data_permissions: tuple[DataPermission, ...] = ()
    data_permission_policy_version: str = FUNDAMENTALS_DATA_PERMISSION_VERSION
    owner_policy: OwnerTaskPolicy
    allowed_model_routes: tuple[RouteId, ...] = ()
    requested_route: RouteId | None = None
    resolved_route: RouteId | None = None
    observed_route: Literal["UNKNOWN_AT_CONFIRM"] = "UNKNOWN_AT_CONFIRM"
    selection_origin: Literal["USER_EXPLICIT", "PROFILE_DEFAULT", "SYSTEM_DEFAULT"]
    profile_default_route: RouteId | None = None
    recovery_fallback_routes: tuple[RouteId, ...] = ()
    recovery_budget: RecoveryBudget | None = None
    envelope_source: Literal["PROFILE_DEFAULT", "EXPLICIT_CONFIGURATION"] = "PROFILE_DEFAULT"
    envelope_classification: Literal["PROFILE_POLICY"] = "PROFILE_POLICY"
    # Secret-free configuration identity, never credentials or prompts.
    runtime_configuration: dict = Field(default_factory=dict)
    runtime_configuration_digest: str | None = None
    evidence_requirement: str = "ACCEPTED_INPUTS_AND_PROVENANCE"
    review_gate: str = "EXISTING_INDEPENDENT_REVIEW_BEFORE_RELEASE"
    stop_conditions: tuple[str, ...]

    accepted_request_proof: AcceptedRequestProof | None = None

    @model_serializer(mode="wrap")
    def preserve_snapshot_codec(self, handler):
        values = handler(self)
        # An absent extension has exactly the historical serialized shape and hash.
        if self.accepted_request_proof is None:
            values.pop("accepted_request_proof", None)
        return values

    @property
    def allowed_data_capability_ids(self):
        return tuple(p.capability_id for p in self.data_permissions)

    def require_method(self, method):
        if method not in self.allowed_method_ids:
            raise BindingDenied("METHOD_NOT_AUTHORIZED", method)

    def require_tool(self, tool):
        if tool not in self.allowed_tool_ids:
            raise BindingDenied("TOOL_NOT_AUTHORIZED", tool)

    def require_route(self, route):
        if route not in self.allowed_model_routes:
            raise BindingDenied("MODEL_NOT_AUTHORIZED", route)

    def data_permission(self, capability, *, scope=None, provider=None):
        matches = [
            p
            for p in self.data_permissions
            if p.capability_id == capability and (scope is None or p.data_scope_id == scope)
        ]
        if len(matches) != 1 or (provider is not None and provider not in matches[0].providers):
            raise BindingDenied("DATA_CAPABILITY_NOT_AUTHORIZED", capability)
        return matches[0]

    @model_validator(mode="after")
    def closed_envelope(self):
        if self.runtime_configuration_digest != digest(
            self.runtime_configuration, "execution-composition/v1"
        ):
            raise ValueError("Corrupt runtime configuration snapshot")
        if self.task_type != self.owner_policy.task_profile:
            raise ValueError("Task policy identity mismatch")
        if not set(self.allowed_model_routes) <= set(self.owner_policy.candidates):
            raise ValueError("Profile cannot expand Owner model permission")
        if self.requested_route is not None:
            self.require_route(self.requested_route)
        if not set(self.recovery_fallback_routes) <= set(self.allowed_model_routes):
            raise ValueError("Fallback cannot expand model permission")
        if any(p.data_scope_id not in self.data_scope_ids for p in self.data_permissions):
            raise ValueError("Data permission outside frozen scope")
        keys = [(p.data_scope_id, p.capability_id) for p in self.data_permissions]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate data permission")
        return self


class NodeProfileBinding(BindingValue):
    output_contract_digest: str
    task_id: str
    profile: NodeExecutionProfile


class ExecutionSnapshot(BindingValue):
    schema_version: Literal["confirmed-execution-profile/v1"] = "confirmed-execution-profile/v1"
    scenario: ScenarioProfile
    nodes: tuple[NodeProfileBinding, ...]
    scenario_snapshot_digest: str
    execution_profile_snapshot_digest: str

    @classmethod
    def freeze(cls, scenario, nodes):
        nodes = tuple(
            NodeProfileBinding.model_validate(n.model_dump())
            for n in sorted(nodes, key=lambda n: n.task_id)
        )
        return cls(
            scenario=scenario,
            nodes=nodes,
            scenario_snapshot_digest=digest(scenario, "scenario-profile/v1"),
            execution_profile_snapshot_digest=digest(nodes, "node-execution-profiles/v1"),
        )

    @model_validator(mode="after")
    def valid_identity(self):
        if (
            self.scenario_snapshot_digest != digest(self.scenario, "scenario-profile/v1")
            or self.execution_profile_snapshot_digest
            != digest(self.nodes, "node-execution-profiles/v1")
            or len({n.task_id for n in self.nodes}) != len(self.nodes)
        ):
            raise ValueError("Corrupt execution profile digest or duplicate node")
        return self

    def for_task(self, task):
        found = [n.profile for n in self.nodes if n.task_id == task.task_id]
        if len(found) != 1 or found[0].task_type != task.task_type:
            raise BindingDenied("PROFILE_BINDING_MISSING", task.task_id)
        return found[0]
