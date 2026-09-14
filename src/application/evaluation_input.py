"""WP05 detached evidence projection. No I/O, execution or upstream authority.

Snapshot wire format: {source_namespace, records, retained_json?}.
Records: {owner, source_id, payload, content_digest, evidence_scope} with digest
wp05-source-object/v1. Repository/run_id carries native NodeBindingState;
Application/run_id optionally carries native Run. Blob/raw-sha256 carries exact
UTF-8 artifact text. Review/run_id and Release/run_id carry native records.
Method/calculation_id carries selected WP04 metadata plus its native lineage.
For retained fixtures retained_json is the *original* file text; its SHA binds
namespace, its root is used directly (never an overriding Repository record).
For detached bundles the namespace binds the sorted owner/id/digest record set.
Exporters supply evidence; hashes check consistency, not exporter authenticity.
"""

from __future__ import annotations

import hashlib
import json
import re
from uuid import NAMESPACE_URL, uuid5

SCHEMA = "vefin-evaluation-input/v1"
POLICY = "WP05_WP03_VALUATION_TASK_RESULT_READINESS_V1"
SUBJECT = "WP03_VALUATION_TASK_RESULT"
BASELINE = "e290403578cd5485bcee53649ae14f835905d484"
PROFILE = ("valuation_analysis", "valuation_analyst", "valuation_analysis_v1")
METRICS = (
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "reasoning_output_tokens",
    "cost",
    "model_turn_elapsed",
    "provider_only_latency",
)
CORE_REASONS = {
    "MISSING_RESULT_BINDING",
    "STALE_RESULT_POINTER",
    "IDENTITY_MISMATCH",
    "MISSING_CONTEXT_IDENTITY",
    "USAGE_IDENTITY_MISMATCH",
    "INCOMPLETE_DISPATCH_SET",
    "UNSUPPORTED_PROFILE",
    "STALE_SOURCE",
}
EvaluationInputEnvelope = dict


def _json(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(v, tag="wp02-node-binding/v1"):
    return "sha256:" + hashlib.sha256(_json({"schema": tag, "value": v}).encode()).hexdigest()


def _raw(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _without(d, *keys):
    return {k: v for k, v in d.items() if k not in keys}


def _plain(v, depth=0):
    if depth > 80:
        raise ValueError("depth")
    if type(v) in (str, int, float, bool) or v is None:
        return
    if type(v) is list:
        for x in v:
            _plain(x, depth + 1)
        return
    if type(v) is dict and all(type(k) is str for k in v):
        for x in v.values():
            _plain(x, depth + 1)
        return
    raise ValueError("detached JSON only")


def _id(v):
    if v is None or v == "UNKNOWN":
        return None
    if type(v) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}", v):
        raise ValueError("unsafe identity")
    return v


def _pick(d, keys):
    return {k: d.get(k) for k in keys.split()}


def _unknown(reason="ABSENT_SOURCE_FIELD", refs=()):
    return dict(
        value=None,
        provenance="UNKNOWN",
        source_refs=list(refs),
        missing_reason=reason,
        derivation_rule=None,
    )


def _field_refs(refs, native_field):
    return [
        {**ref, "field_selectors": [ref["field_selectors"][0] + "/" + native_field]} for ref in refs
    ]


def _known(value, provenance, refs, rule=None):
    if value is None or value == "UNKNOWN":
        return _unknown(refs=refs)
    return dict(
        value=value,
        provenance=provenance,
        source_refs=list(refs),
        missing_reason=None,
        derivation_rule=rule,
    )


def _digest_id(value):
    return type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


# Declarative closed output types. Schema labels are literals at their exact
# position, never a recursive exemption based on a caller-controlled key name.
def _shape(value, spec):
    if isinstance(spec, dict):
        if type(value) is not dict or set(value) != set(spec):
            raise ValueError("closed object")
        for key, child in spec.items():
            _shape(value[key], child)
    elif isinstance(spec, list):
        if type(value) is not list:
            raise ValueError("typed list")
        for child in value:
            _shape(child, spec[0])
    elif isinstance(spec, tuple):
        if value is not None:
            _shape(value, spec[0])
    elif isinstance(spec, set):
        if type(value) is not str or value not in spec:
            raise ValueError("native enum")
    elif spec == "id":
        if type(value) is not str or _id(value) is None:
            raise ValueError("required identity")
    elif spec == "digest":
        if not _digest_id(value):
            raise ValueError("digest")
    elif spec == "int":
        if type(value) is not int or value < 0:
            raise ValueError("counter")
    elif spec == "bool":
        if type(value) is not bool:
            raise ValueError("boolean")
    elif spec == "selector":
        if type(value) is not str or value not in SAFE_SELECTORS:
            raise ValueError("field selector")
    else:
        raise ValueError("unknown projection type")


CALL_FIELDS = set(
    (
        "schema_version interaction_id turn_number call_id pre_call_B_ref "
        "context_id context_revision request_manifest_digest requested_model "
        "requested_reasoning_profile route_ref requested_route resolved_route "
        "configuration_snapshot resolved_model resolved_provider "
        "observed_provider observed_model provider_identity_source "
        "model_identity_source observed_reasoning response_request_id "
        "fallback_used fallback_from fallback_to fallback_reason "
        "fallback_policy_ref phase input_tokens output_tokens usage_coverage "
        "cost elapsed_ms outcome_digest diagnostic_code "
        "client_physical_dispatch_count provider_internal_fanout"
    ).split()
)
CALL_METRIC_FIELDS = {"input_tokens", "output_tokens", "elapsed_ms"}
SAFE_SELECTORS = {"/", "/payload_snapshot/execution_receipt"} | {
    "/payload_snapshot/execution_receipt/" + field
    for field in (
        "requested_model",
        "resolved_model",
        "resolved_provider",
        "observed_model",
        "observed_provider",
        "input_tokens",
        "output_tokens",
        "elapsed_ms",
        "configuration_snapshot/provider",
    )
}
# Exact admitted schemas from native ValuationTurn and StandardResearchAgentStructuredOutput.
RESPONSE_SCHEMAS = {
    1: "sha256:3a202039b04e6bdfbd05c52d0f4be34f4a81f2ed9c2b88a685715fabcfc354bd",
    2: "sha256:9d9a1310e5cdfc35be22e6b867d8871dda22c6fb2f4d4882bf09827ce8ad1c16",
}
NS_SHAPE = {
    "kind": {"RETAINED_LOCAL_FIXTURE", "DETACHED_OWNER_SNAPSHOT"},
    "anchor_digest": "digest",
}
REF_SHAPE = dict(
    source_namespace=NS_SHAPE,
    owner="id",
    source_id="id",
    content_digest="digest",
    field_selectors=["selector"],
    evidence_scope={"RETAINED_LOCAL_FIXTURE", "DETACHED_OWNER_SNAPSHOT", "SYNTHETIC_CONTEXT"},
    producer_baseline={BASELINE},
)
GRAPH_SHAPE = dict(run_id="id", graph_id="id", version="int", semantic_hash="digest")
CHECK_SHAPE = dict(code="id", status={"PASS", "BLOCK", "REVIEW"}, subject_refs=["id"])
PROVENANCE = {
    "PROVIDER_RESPONSE",
    "CLIENT_OBSERVATION",
    "RUNTIME_MEASUREMENT",
    "DERIVED_FROM_OBSERVED",
    "CONFIGURED",
    "UNKNOWN",
}


def _evidence(value, scalar):
    _shape(
        value,
        dict(
            value=(scalar,),
            provenance=PROVENANCE,
            source_refs=[REF_SHAPE],
            missing_reason=(
                {
                    "ABSENT_SOURCE_FIELD",
                    "NO_EXACT_JOIN",
                    "NO_BILLING_AUTHORITY",
                    "NOT_RETAINED",
                    "NOT_APPLICABLE",
                    "UNPROVEN_DEFAULT",
                    "INCOMPLETE_MEMBERSHIP",
                },
            ),
            derivation_rule=(
                {
                    "MODEL_TURN_ELAPSED",
                    "SUM_MODEL_TURN_ELAPSED",
                    "WP05_SUM_EXACT_DISPATCH_FIELD_V1",
                },
            ),
        ),
    )
    if value["provenance"] == "UNKNOWN":
        if (
            value["value"] is not None
            or not value["missing_reason"]
            or value["derivation_rule"] is not None
        ):
            raise ValueError("unknown evidence")
    elif value["value"] is None or not value["source_refs"] or value["missing_reason"] is not None:
        raise ValueError("unproven evidence")


def _native_selectors(value):
    allowed = {
        "/",
        "structured_output",
        "structured_output.summary",
        "/structured_output",
        "/structured_output/summary",
    }
    if (
        type(value) is not list
        or not value
        or any(type(x) is not str or x not in allowed for x in value)
    ):
        raise ValueError("native field selectors")


def _answer_shape(value):
    if type(value) is not dict or set(value) != {
        "summary",
        "key_findings",
        "risks",
        "limitations",
        "requires_follow_up",
    }:
        raise ValueError("response shape")
    if (
        type(value["summary"]) is not str
        or not 1 <= len(value["summary"].strip()) <= 800
        or value["requires_follow_up"] is not False
    ):
        raise ValueError("response scalar")
    for key in ("key_findings", "risks", "limitations"):
        items = value[key]
        if (
            type(items) is not list
            or len(items) > 5
            or any(type(x) is not str or not 1 <= len(x.strip()) <= 800 for x in items)
        ):
            raise ValueError("response list")
        if len(set(items)) != len(items) or (key == "key_findings" and not items):
            raise ValueError("response membership")


def _export_shape(out):
    identity_fields = (
        "run_id task_id task_fingerprint admission_binding_id result_id "
        "result_digest current_result_id final_context_id "
        "final_context_manifest_digest interaction_id"
    )
    member = dict(
        call_id="id", pre_B_id="id", receipt_B_id="id", context_id="id", context_revision="int"
    )
    subject = {k: "id" for k in identity_fields.split()}
    subject.update(
        source_namespace=NS_SHAPE,
        subject_type={SUBJECT},
        graph=GRAPH_SHAPE,
        ordered_B_ids=["id"],
        result_version="int",
        final_context_revision="int",
        dispatch_membership=[member],
    )
    turn = dict(
        context_id="id",
        context_revision="int",
        source_manifest_digest="digest",
        pre_B_id="id",
        request_manifest_digest="digest",
        response_schema_digest="digest",
    )
    review = dict(
        review_id="id",
        run_id="id",
        reviewer="id",
        status={"PASS", "BLOCK", "REVIEW"},
        input_snapshot_hash="digest",
        record_digest="digest",
        requirement_context_digest="digest",
        reviewed_subject_refs=["id"],
        checks=[CHECK_SHAPE],
        scope={"RUN_CONTEXT_ONLY"},
        source_refs=[REF_SHAPE],
    )
    method = {
        k: ("id",)
        for k in (
            "capability_id capability_version formula_id formula_version "
            "implementation_hash descriptor_digest source_manifest_digest "
            "semantic_policy_digest decimal_policy_digest input_identity_digest "
            "requirement_id B_ref observation_id diagnostic_code "
            "actual_flags_digest"
        ).split()
    }
    method.update(
        calculation_id="id",
        applicability={"APPLICABLE"},
        support_status={"SUPPORTED"},
        numeric_outcome={"SUCCEEDED"},
        source_refs=[REF_SHAPE],
    )
    # EvidenceValues are checked separately with the field-specific scalar type.
    dispatch = {
        k: ("id",)
        for k in (
            "dispatch_id pre_B_id receipt_B_id interaction_id context_id "
            "request_manifest_digest outcome_digest response_request_id "
            "diagnostic_code"
        ).split()
    }
    dispatch.update(
        model_turn="int",
        context_revision="int",
        status={"RESERVED", "DISPATCHED", "RESPONSE", "FAILED", "RESULT_UNKNOWN"},
        authority_status={"COMMITTED", "RETAINED_TEST_OBSERVATION"},
        model_identity_source={"UNKNOWN", "PROVIDER_RESPONSE"},
        provider_identity_source={"UNKNOWN", "CLIENT_DISPATCH"},
    )
    evidence_fields = set(METRICS) | {
        "physical_dispatch_count",
        "requested_model",
        "requested_provider",
        "resolved_model",
        "resolved_provider",
        "observed_model",
        "observed_provider",
    }
    for d in out["dispatches"]:
        if type(d) is not dict or set(d) != set(dispatch) | evidence_fields:
            raise ValueError("dispatch shape")
        _shape({k: d[k] for k in dispatch}, dispatch)
        for k in evidence_fields:
            _evidence(d[k], "int" if k in METRICS or k == "physical_dispatch_count" else "id")
    aggregate = out["usage_aggregate"]
    if type(aggregate) is not dict or set(aggregate) != {"membership_complete", *METRICS}:
        raise ValueError("aggregate shape")
    _shape(aggregate["membership_complete"], "bool")
    for k in METRICS:
        m = aggregate[k]
        fields = dict(
            expected_dispatch_count=("int",),
            observed_metric_count="int",
            complete_for_metric="bool",
            unknown_dispatch_ids=["id"],
        )
        if type(m) is not dict or set(m) != {*fields, "observed_subtotal", "complete_total"}:
            raise ValueError("metric shape")
        _shape({k: m[k] for k in fields}, fields)
        _evidence(m["observed_subtotal"], "int")
        _evidence(m["complete_total"], "int")
    fields = dict(
        schema_version={SCHEMA},
        readiness_policy_id={POLICY},
        subject_type={SUBJECT},
        subject_id=("digest",),
        subject_identity=(subject,),
        task_identity=(
            {
                **{k: ("id",) for k in "run_id task_id task_type assigned_agent skill_id".split()},
                "task_fingerprint": "digest",
            },
        ),
        graph_identity=(GRAPH_SHAPE,),
        result_identity=(
            {
                **{
                    k: ("id",)
                    for k in (
                        "result_id result_digest current_result_id admission_binding_id status "
                        "reservation_id"
                    ).split()
                },
                "result_version": ("int",),
                "owner_generation": ("int",),
                "ordered_B_ids": ["id"],
            },
        ),
        context_identity=(
            {"turns": [turn], "final_context_id": "id", "final_context_revision": "int"},
        ),
        dependency_identity=[
            dict(
                kind="id",
                owner="id",
                source_id="id",
                content_digest="digest",
                producer_task_id=("id",),
                result_id=("id",),
                result_version=("int",),
                field_selectors=["selector"],
            )
        ],
        review_context=(review,),
        release_context=(
            dict(
                run_status=(
                    {
                        "DRAFT",
                        "SCHEME_GENERATING",
                        "AWAITING_CONFIRMATION",
                        "PLANNING",
                        "RUNNING",
                        "REVIEW",
                        "PROVING",
                        "RELEASED",
                        "FAILED",
                        "CANCELLED",
                    },
                ),
                released_result_id=("id",),
                released_result_digest=("digest",),
                canonical_record_id=("id",),
                scope={"RUN_CONTEXT_ONLY"},
                source_refs=[REF_SHAPE],
            ),
        ),
        method_dependency_context=[method],
        readiness_state={"READY", "PARTIALLY_READY", "NOT_READY", "LEGACY_UNKNOWN"},
        readiness_reasons=[
            CORE_REASONS
            | {
                "MISSING_MODEL_OBSERVATION",
                "MISSING_USAGE_PROVENANCE",
                "MISSING_TURN_MEASUREMENT",
                "MISSING_REVIEW",
                "METHOD_IDENTITY_UNKNOWN",
                "LEGACY_METADATA_ABSENT",
            }
        ],
        safe_source_manifest=[REF_SHAPE],
        envelope_digest=("digest",),
    )
    if set(out) != {*fields, "dispatches", "usage_aggregate"}:
        raise ValueError("envelope shape")
    _shape({k: out[k] for k in fields}, fields)


class _Projection:
    def __init__(self):
        self.reasons = set()
        self.records = {}
        self.manifest = []
        self.namespace = None
        self.root = {}
        self.legacy = False
        self.contexts = []
        self.dependencies = {}
        self.methods = {}
        self.valid_bs = {}
        self.materials = {}
        self.used = set()
        self.out = dict(
            schema_version=SCHEMA,
            readiness_policy_id=POLICY,
            subject_type=SUBJECT,
            subject_id=None,
            subject_identity=None,
            task_identity=None,
            graph_identity=None,
            result_identity=None,
            context_identity=None,
            dependency_identity=[],
            dispatches=[],
            usage_aggregate={},
            review_context=None,
            release_context=None,
            method_dependency_context=[],
            readiness_state="NOT_READY",
            readiness_reasons=[],
            safe_source_manifest=[],
            envelope_digest=None,
        )

    def check(self, condition, reason="IDENTITY_MISMATCH"):
        if not condition:
            self.reasons.add(reason)
        return bool(condition)

    def ref(self, owner, identity, payload, selector="/", tag=None):
        ref = dict(
            source_namespace=self.namespace,
            owner=_id(owner),
            source_id=_id(identity),
            content_digest=_hash(payload, tag or "wp05-source-object/v1"),
            field_selectors=[selector],
            evidence_scope="RETAINED_LOCAL_FIXTURE"
            if self.namespace["kind"] == "RETAINED_LOCAL_FIXTURE"
            else "DETACHED_OWNER_SNAPSHOT",
            producer_baseline=BASELINE,
        )
        record = self.records.get((owner, identity))
        if record:
            ref["evidence_scope"] = record["evidence_scope"]
            self.used.add((owner, identity))
        self.manifest.append(ref)
        return [ref]

    def object(self, owner, identity):
        r = self.records.get((owner, identity))
        if r:
            self.used.add((owner, identity))
            return r["payload"]
        return None

    def load(self, snapshot, selector):
        ns = snapshot["source_namespace"]
        if set(ns) != {"kind", "anchor_digest"} or ns["kind"] not in {
            "RETAINED_LOCAL_FIXTURE",
            "DETACHED_OWNER_SNAPSHOT",
        }:
            raise ValueError("namespace")
        self.namespace = ns
        for r in snapshot.get("records", []):
            key = (r["owner"], r["source_id"])
            if key in self.records:
                raise ValueError("duplicate source")
            if r["owner"] not in {
                "Repository",
                "Application",
                "Blob",
                "Review",
                "Release",
                "Method",
                "ContextSource",
            }:
                raise ValueError("owner")
            _id(key[1])
            if r["evidence_scope"] not in {
                "DETACHED_OWNER_SNAPSHOT",
                "RETAINED_LOCAL_FIXTURE",
                "SYNTHETIC_CONTEXT",
            }:
                raise ValueError("scope")
            if r["content_digest"] != _hash(r["payload"], "wp05-source-object/v1"):
                raise ValueError("source digest")
            self.records[key] = r
        members = sorted(
            [_pick(r, "owner source_id content_digest") for r in self.records.values()],
            key=lambda r: (r["owner"], r["source_id"], r["content_digest"]),
        )
        if ns["kind"] == "RETAINED_LOCAL_FIXTURE":
            text = snapshot["retained_json"]
            if ns["anchor_digest"] != _raw(text) or any(k[0] == "Repository" for k in self.records):
                raise ValueError("retained identity")
            doc = json.loads(text)
            self.root = doc.get("root")
            self.diagnostic_calls = doc.get("receipts", [])
            self.check(doc.get("valuation_task", selector["task_id"]) == selector["task_id"])
        else:
            if ns["anchor_digest"] != _hash(members, "wp05-source-bundle/v1"):
                raise ValueError("bundle identity")
            self.root = self.object("Repository", selector["run_id"])
            self.diagnostic_calls = []
        self.check(selector["source_namespace"] == ns)
        self.run_id, self.task_id = _id(selector["run_id"]), _id(selector["task_id"])
        self.ref("Repository", self.run_id, self.root)
        run = self.object("Application", self.run_id)
        if run:
            self.check(run["run_id"] == self.run_id)
        self.run = run or {}
        if self.root is None:
            self.legacy = bool(
                run
                and run.get("run_id") == self.run_id
                and not run.get("node_binding")
                and not run.get("wp03_context")
            )
            self.check(self.legacy, "MISSING_RESULT_BINDING")
            return False
        self.check(self.root["run_id"] == self.run_id)
        return True

    def native(self, v, field, *exclude):
        return self.check(v.get(field) == _hash(_without(v, field, *exclude), v["schema_version"]))

    def material(self, m):
        payload = m["payload_snapshot"]
        ok = self.check(m["content_digest"] == _hash(payload, m["record_schema"]))
        identity = m["record_id"]
        previous = self.materials.get(identity)
        if previous:
            ok &= self.check(previous == m)
        if ok:
            if m["kind"] == "EVIDENCE":
                blob_id = payload.get("snapshot_hash", "")
                blob_id = blob_id if blob_id.startswith("sha256:") else "sha256:" + blob_id
                blob = self.object("Blob", blob_id)
                if blob is None:
                    self.reasons.add("MISSING_CONTEXT_IDENTITY")
                else:
                    ok &= self.check(_raw(blob) == blob_id)
            self.materials[identity] = m
        return ok

    def binding(self, bid, admission):
        b = self.root["resolved_inputs"].get(bid)
        if not b:
            self.reasons.add("INCOMPLETE_DISPATCH_SET")
            return None
        ok = self.native(b, "resolved_input_binding_id")
        ok &= self.check(
            bid == b["resolved_input_binding_id"]
            and b["admission_binding_id"] == admission["admission_binding_id"]
            and b["reservation_id"] == admission["attempt_reservation_id"]
            and b["input_digest"] == _hash(b["payload_snapshot"], "wp02-input-payload/v1")
        )
        for m in b["material_refs"]:
            ok &= self.material(m)
        if ok:
            self.valid_bs[bid] = b
            return b
        return None

    def context(self, k, pre, call):
        refs = [k[f] for f in ("goal_ref", "scheme_ref", "graph_ref", "admission_binding_ref")]
        for field in (
            "dependency_result_refs",
            "evidence_refs",
            "calculation_refs",
            "claim_metric_refs",
            "resolved_issue_refs",
            "ancestor_output_refs",
            "retrieval_history_refs",
        ):
            refs += k[field]
        native_ref = dict(
            namespace={"CURRENT"},
            owner="id",
            object_id="id",
            run_id="id",
            source_id="id",
            source_schema="id",
            version=("int",),
            source_digest="digest",
            field_selectors=["id"],
            inclusion_reason="id",
        )
        # Native schema tags and known selectors are checked in place; neither
        # is exported as an arbitrary string.
        for ref in refs:
            if type(ref) is not dict or set(ref) != set(native_ref):
                raise ValueError("native source ref")
            _shape(
                _pick(ref, "owner object_id run_id source_id source_digest inclusion_reason"),
                {
                    k: "id"
                    for k in (
                        "owner",
                        "object_id",
                        "run_id",
                        "source_id",
                        "source_digest",
                        "inclusion_reason",
                    )
                },
            )
            self.check(
                ref["namespace"]
                == ("INTERACTION" if ref["owner"] == "ValuationInteraction" else "CURRENT")
                and ref["run_id"] == self.run_id
                and ref["object_id"] == self.a["object_id"]
            )
            if type(ref["source_schema"]) is not str or ref["source_schema"] not in {
                "wp02-admission/v1",
                "wp02-node-binding/v1/graph",
                "wp02-result/v1",
                "agent-output-record/v1",
                "retrieval-request/v1",
                "evidence-record/v1",
                "calculation-core/v1",
                "wp02-node-binding/v1",
            }:
                raise ValueError("native source schema")
            _native_selectors(ref["field_selectors"])
        self.check(
            k["goal_ref"]["source_id"] == self.a["goal_id"]
            and k["scheme_ref"]["source_id"] == self.a["scheme_id"]
            and k["graph_ref"]["source_id"] == self.a["graph"]["graph_id"]
        )
        ordered = sorted(
            refs, key=lambda r: (r["namespace"], r["owner"], r["source_id"], r["field_selectors"])
        )
        ok = self.check(k["source_manifest_digest"] == _hash(ordered, "context-manifest/v1"))
        body = _without(k, "context_id", "size_bytes", "created_at")
        ok &= self.check(k["context_id"] == _hash(body, "vefin-research-context/v1"))
        ok &= self.check(
            k["size_bytes"] == len(_json({**body, "context_id": k["context_id"]}).encode())
        )
        a = self.a
        ok &= self.check(
            k["freshness_receipt"]["admission_digest"] == _hash(a)
            and k["freshness_receipt"]["memory_digest"] == _hash(k["memory_binding"])
        )
        ok &= self.check(
            k["run_id"] == self.run_id
            and k["task_id"] == self.task_id
            and k["task_fingerprint"] == a["task_fingerprint"]
            and k["context_id"] == call["context_id"]
            and k["context_revision"] == call["context_revision"]
            and k["consumer_role"] == PROFILE[1]
            and k["requested_model"] == call["requested_model"]
            and k["routing_policy_ref"] == call["route_ref"]
        )
        self.check(k["memory_binding"].get("mode") in {"NONE", "BOUND"})
        ok &= self.check(
            k["goal_ref"]["source_digest"] == a["goal_hash"]
            and k["scheme_ref"]["source_digest"] == a["scheme_hash"]
            and k["graph_ref"]["source_digest"] == a["graph"]["semantic_hash"]
            and k["admission_binding_ref"]["source_digest"] == _hash(a, a["schema_version"])
            and k["admission_binding_ref"]["source_id"] == a["admission_binding_id"]
        )
        for ref in refs[4:]:
            sid, owner = ref["source_id"], ref["owner"]
            payload = None
            if owner == "Repository":
                expected_dep = next(
                    (d for d in a["dependency_result_bindings"] if d["result_id"] == sid), None
                )
                self.check(expected_dep is not None)
                payload = self.root["results"].get(sid)
                if payload:
                    self.check(
                        sid == self.root["current_results"].get(payload["producer_task_id"]),
                        "STALE_RESULT_POINTER",
                    )
                    self.native(payload, "result_digest", "result_id")
                    if expected_dep:
                        self.check(
                            all(payload.get(key) == value for key, value in expected_dep.items())
                        )
                    self.check(sid not in self.root["invalidation_refs"])
            elif owner == "ValuationInteraction":
                matches = [
                    b["payload_snapshot"].get("response", {}).get("request")
                    for b in self.valid_bs.values()
                    if isinstance(b["payload_snapshot"].get("response"), dict)
                ]
                request = next((x for x in matches if x and x.get("request_id") == sid), None)
                payload = _without(request, "request_id") if request else None
            elif sid in self.materials:
                payload = self.materials[sid]["payload_snapshot"]
            else:
                payload = self.object("ContextSource", sid)
            if payload is None:
                self.reasons.add("MISSING_CONTEXT_IDENTITY")
            else:
                self.check(ref["source_digest"] == _hash(payload, ref["source_schema"]))
            self.dependencies[(owner, sid)] = dict(
                kind=owner,
                owner=_id(owner),
                source_id=_id(sid),
                content_digest=ref["source_digest"],
                producer_task_id=payload.get("producer_task_id")
                if isinstance(payload, dict)
                else None,
                result_id=sid if owner == "Repository" else None,
                result_version=ref.get("version"),
                field_selectors=["/"],
            )
            if owner == "CALCULATION_CORE" and payload:
                self.methods[sid] = payload
        self.contexts.append(
            dict(
                context_id=k["context_id"],
                context_revision=k["context_revision"],
                source_manifest_digest=k["source_manifest_digest"],
                pre_B_id=pre["resolved_input_binding_id"],
                request_manifest_digest=pre["payload_snapshot"]["request_manifest_digest"],
                response_schema_digest=pre["payload_snapshot"]["response_schema_digest"],
            )
        )
        return ok

    def call(self, c, post):
        if type(c) is not dict or set(c) - CALL_FIELDS - {"retry_used"}:
            raise ValueError("CallReceipt fields")
        schema_ok = self.check(c.get("schema_version") == "vefin-context-model-call/v1")
        for key in (
            CALL_FIELDS
            - CALL_METRIC_FIELDS
            - {
                "schema_version",
                "configuration_snapshot",
                "fallback_used",
                "turn_number",
                "context_revision",
                "client_physical_dispatch_count",
            }
        ):
            if c.get(key) is not None:
                value = c[key]
                if key == "fallback_policy_ref":
                    self.check(value == "wp03-valuation-context-interaction/v1")
                elif value != "UNKNOWN":
                    _shape(value, "id")
        self.check(
            c.get("fallback_used") is False
            and c.get("retry_used", False) is False
            and c.get("fallback_from") is None
            and c.get("fallback_to") is None
            and c.get("fallback_reason") == "NO_FALLBACK_IN_WP03_V1",
            "UNSUPPORTED_PROFILE",
        )
        bid = c.get("pre_call_B_ref")
        pre = self.valid_bs.get(bid)
        if pre is None:
            self.reasons.add("INCOMPLETE_DISPATCH_SET")
        phase = c.get("phase")
        if phase not in {"RESERVED", "DISPATCHED", "RESPONSE", "FAILED", "RESULT_UNKNOWN"}:
            self.reasons.add("USAGE_IDENTITY_MISMATCH")
            return None
        if c.get("client_physical_dispatch_count") == 0:
            return None
        if (
            type(c.get("client_physical_dispatch_count")) is not int
            or c["client_physical_dispatch_count"] != 1
        ):
            self.reasons.add("USAGE_IDENTITY_MISMATCH")
            return None
        t = c["turn_number"]
        if type(t) is not int or t not in (1, 2):
            raise ValueError("turn")
        self.check(
            c["interaction_id"] == self.interaction and c["call_id"] == f"{self.interaction}:{t}:1",
            "USAGE_IDENTITY_MISMATCH",
        )
        linked = bool(post and pre and schema_ok)
        if linked:
            self.check(
                post["step_id"] == f"wp03:valuation:turn:{t}:receipt"
                and pre["step_id"] == f"wp03:valuation:context:{t}",
                "USAGE_IDENTITY_MISMATCH",
            )
            payload = pre["payload_snapshot"]
            config = payload["configuration_snapshot"]
            self.check(
                config == c.get("configuration_snapshot")
                and c["route_ref"] == _hash(config, "wp03-route-config/v1")
            )
            self.check(
                config.get("task_profile") == PROFILE[0]
                and config.get("fallback_allowed") is False
                and config.get("retry_allowed") is False
                and config.get("recovery_enabled") is False
                and config.get("transport") == "OWNED_DIRECT_NO_RETRY_NO_REDIRECT"
                and config.get("execution_policy", {}).get("max_attempts") == 1,
                "UNSUPPORTED_PROFILE",
            )
            self.check(
                c.get("resolved_model") == c["requested_model"] == config.get("model")
                and c.get("resolved_provider") == config.get("provider")
                and c.get("resolved_route") == c.get("requested_route") == config.get("route")
                and c["request_manifest_digest"] == payload["request_manifest_digest"]
            )
            self.check(payload["response_schema_digest"] == RESPONSE_SCHEMAS[t])
            response = post["payload_snapshot"].get("response")
            if response is not None:
                self.check(c.get("outcome_digest") == _hash(response))
            else:
                self.check(c.get("outcome_digest") is None)
            if self.r:
                self.check(phase == "RESPONSE" and c.get("diagnostic_code") is None)
                if t == 1:
                    self.check(
                        type(response) is dict and set(response) == {"kind", "answer", "request"}
                    )
                    if self.expected == 2:
                        self.check(
                            response.get("kind") == "RETRIEVE"
                            and response.get("answer") is None
                            and type(response.get("request")) is dict
                        )
                    else:
                        self.check(
                            response.get("kind") == "FINAL"
                            and response.get("request") is None
                            and type(response.get("answer")) is dict
                        )
                else:
                    self.check(
                        type(response) is dict and "summary" in response and "kind" not in response
                    )
            if c.get("observed_model") not in (None, "UNKNOWN"):
                self.check(c["observed_model"] == c["requested_model"])
            if c.get("observed_provider") not in (None, "UNKNOWN"):
                self.check(c["observed_provider"] == c["resolved_provider"])
            if self.r and t == self.expected:
                answer = response["answer"] if t == 1 else response
                _answer_shape(answer)
                self.final_response = answer
            self.context(payload["context_package"], pre, c)
        refs = (
            self.ref(
                "Repository",
                post["resolved_input_binding_id"],
                post,
                "/payload_snapshot/execution_receipt",
                post["schema_version"],
            )
            if post
            else self.ref("Repository", c["call_id"], c)
        )
        result = dict(
            dispatch_id=_id(c["call_id"]),
            model_turn=t,
            pre_B_id=_id(bid),
            receipt_B_id=post["resolved_input_binding_id"] if post else None,
            interaction_id=_id(c["interaction_id"]),
            context_id=_id(c["context_id"]),
            context_revision=c["context_revision"],
            request_manifest_digest=_id(c.get("request_manifest_digest")),
            outcome_digest=_id(c.get("outcome_digest")),
            response_request_id=_id(c.get("response_request_id")),
            status=phase,
            diagnostic_code=_id(c.get("diagnostic_code")),
            authority_status="COMMITTED" if post else "RETAINED_TEST_OBSERVATION",
            physical_dispatch_count=_known(1, "CLIENT_OBSERVATION", refs),
            model_identity_source=c.get("model_identity_source", "UNKNOWN"),
            provider_identity_source=c.get("provider_identity_source", "UNKNOWN"),
        )
        self.check(
            result["model_identity_source"] in {"UNKNOWN", "PROVIDER_RESPONSE"}
            and result["provider_identity_source"] in {"UNKNOWN", "CLIENT_DISPATCH"},
            "USAGE_IDENTITY_MISMATCH",
        )
        for field, prov in (
            ("requested_model", "CONFIGURED"),
            ("resolved_model", "CLIENT_OBSERVATION"),
            ("resolved_provider", "CLIENT_OBSERVATION"),
            ("observed_model", "PROVIDER_RESPONSE"),
            ("observed_provider", "CLIENT_OBSERVATION"),
        ):
            evidenced = linked
            if field == "observed_model":
                evidenced &= c.get("model_identity_source") == "PROVIDER_RESPONSE"
            if field == "observed_provider":
                evidenced &= c.get("provider_identity_source") == "CLIENT_DISPATCH"
            result[field] = (
                _known(_id(c.get(field)), prov, _field_refs(refs, field))
                if evidenced
                else _unknown("NO_EXACT_JOIN", refs)
            )
        result["requested_provider"] = (
            _known(
                _id(c.get("configuration_snapshot", {}).get("provider")),
                "CONFIGURED",
                _field_refs(refs, "configuration_snapshot/provider"),
            )
            if linked
            else _unknown()
        )
        for field, native in (
            ("input_tokens", "input_tokens"),
            ("output_tokens", "output_tokens"),
            ("model_turn_elapsed", "elapsed_ms"),
        ):
            value = c.get(native)
            valid = value is None or (type(value) is int and value >= 0)
            self.check(valid, "USAGE_IDENTITY_MISMATCH")
            result[field] = (
                _known(
                    value,
                    "RUNTIME_MEASUREMENT" if field == "model_turn_elapsed" else "PROVIDER_RESPONSE",
                    _field_refs(refs, native),
                    "MODEL_TURN_ELAPSED" if field == "model_turn_elapsed" else None,
                )
                if valid
                and linked
                and (
                    field == "model_turn_elapsed"
                    or c.get("usage_coverage") in {"REPORTED", "PARTIAL_OR_UNKNOWN"}
                )
                else _unknown("UNPROVEN_DEFAULT" if value == 0 else "NO_EXACT_JOIN", refs)
            )
        for field in (
            "cached_input_tokens",
            "reasoning_output_tokens",
            "provider_only_latency",
            "cost",
        ):
            result[field] = _unknown("NO_BILLING_AUTHORITY" if field == "cost" else "NOT_RETAINED")
        for field, reason in (
            ("observed_model", "MISSING_MODEL_OBSERVATION"),
            ("observed_provider", "MISSING_MODEL_OBSERVATION"),
            ("input_tokens", "MISSING_USAGE_PROVENANCE"),
            ("output_tokens", "MISSING_USAGE_PROVENANCE"),
            ("model_turn_elapsed", "MISSING_TURN_MEASUREMENT"),
        ):
            if result[field]["value"] is None:
                self.reasons.add(reason)
        return result

    def core(self):
        root = self.root
        attempt = root["attempts"].get(self.task_id)
        if not attempt:
            self.reasons.add("MISSING_RESULT_BINDING")
            return
        self.a = a = attempt["admission"]
        self.native(a, "admission_binding_id")
        task = a["authorized_input_requirements"]["task"]
        self.check(
            tuple(task.get(k) for k in ("task_type", "assigned_agent", "skill_id")) == PROFILE
            and root["execution_mode"] == "DEFAULT"
            and a["policy_refs"].get("scope") == "fixed-initial-graph-default/v1",
            "UNSUPPORTED_PROFILE",
        )
        self.check(
            a["task_fingerprint"] == _hash(task, "wp02-node-binding/v1/task")
            and a["run_id"] == root["run_id"] == self.run_id
            and task["task_id"] == a["task_id"] == self.task_id
            and a["graph"] == root["frozen_graph"]
            and (
                (
                    a["owner"]["owner_generation"] == root["owner_generation"]
                    and a["owner"]["owner_id"] == root["owner_id"]
                )
                or (
                    root["lifecycle"] == "CLOSED"
                    and root["owner_id"] == a["owner"]["owner_id"]
                    and root["owner_generation"] == a["owner"]["owner_generation"] + 1
                )
            )
        )
        self.check(task["run_id"] == a["graph"]["run_id"] == a["owner"]["run_id"] == self.run_id)
        for app_key, admission_key in (
            ("goal_id", "goal_id"),
            ("scheme_id", "scheme_id"),
            ("research_object_id", "object_id"),
        ):
            if self.run.get(app_key) is not None:
                _shape(self.run[app_key], "id")
                self.check(self.run[app_key] == a[admission_key])
        for key in ("actual_graph_id",):
            if self.run.get(key) is not None:
                self.check(self.run[key] == a["graph"]["graph_id"])
        scheme = a["authorized_input_requirements"]["scheme"]
        for key, expected in (
            ("scheme_id", a["scheme_id"]),
            ("goal_id", a["goal_id"]),
            ("research_object_id", a["object_id"]),
        ):
            if key in scheme:
                self.check(scheme[key] == expected)
        self.check(a["scheme_hash"] == _hash(a["authorized_input_requirements"]["scheme"]))
        self.interaction = _hash(a, "valuation-interaction/v1")
        self.out["task_identity"] = {
            **_pick(task, "run_id task_id task_type assigned_agent skill_id"),
            "task_fingerprint": a["task_fingerprint"],
        }
        self.out["graph_identity"] = a["graph"]
        rid = root["current_results"].get(self.task_id)
        r = root["results"].get(rid)
        self.r = r
        if r is None:
            self.reasons.add("MISSING_RESULT_BINDING" if rid is None else "STALE_RESULT_POINTER")
        else:
            self.native(r, "result_digest", "result_id")
            self.check(
                r["result_id"] == r["result_digest"] == rid
                and rid not in root["invalidation_refs"],
                "STALE_RESULT_POINTER",
            )
            self.check(
                r["status"] == "COMMITTED"
                and attempt["status"] == "COMMITTED"
                and r["run_id"] == self.run_id
                and r["producer_task_id"] == self.task_id
                and r["admission_binding_id"] == a["admission_binding_id"]
                and r["reservation_id"] == a["attempt_reservation_id"]
                and r["owner_generation"] == a["owner"]["owner_generation"]
                and r["graph"] == a["graph"]
                and r["task_fingerprint"] == a["task_fingerprint"]
                and type(r["result_version"]) is int
                and r["result_version"] >= 1
            )
        ids = (
            r["resolved_input_binding_ids"]
            if r
            else [
                key
                for key, b in root["resolved_inputs"].items()
                if b["admission_binding_id"] == a["admission_binding_id"]
            ]
        )
        self.check(len(ids) == len(set(ids)), "INCOMPLETE_DISPATCH_SET")
        for bid in ids:
            self.binding(bid, a)
        summary = r.get("observed_execution", {}).get("wp03_context") if r else None
        if r and not summary:
            self.reasons.add("UNSUPPORTED_PROFILE")
        posts = [
            b
            for b in self.valid_bs.values()
            if b["step_id"].startswith("wp03:valuation:turn:") and b["step_id"].endswith(":receipt")
        ]
        calls = [b["payload_snapshot"]["execution_receipt"] for b in posts]
        if summary:
            self.expected = summary["client_physical_dispatch_count"]
            self.check(
                summary["calls"] == calls
                and summary["receipt_refs"] == [b["resolved_input_binding_id"] for b in posts],
                "INCOMPLETE_DISPATCH_SET",
            )
            self.check(
                type(self.expected) is int
                and self.expected in (1, 2)
                and summary["logical_turn_count"] == self.expected
                and summary["provider_logical_call_count"] == self.expected
                and summary["retrieval_round_count"] == self.expected - 1
                and summary["fallback_count"] == summary["retry_count"] == 0,
                "INCOMPLETE_DISPATCH_SET",
            )
        else:
            self.expected = (
                len([c for c in calls if c["client_physical_dispatch_count"] == 1]) or None
            )

        def counters(counter, count, receipt_ids, prefix):
            self.check(
                type(counter) is dict and counter.get("interaction_id") == self.interaction,
                "INCOMPLETE_DISPATCH_SET",
            )
            self.check(
                counter.get("calls") == prefix and counter.get("receipt_refs") == receipt_ids,
                "INCOMPLETE_DISPATCH_SET",
            )
            for key, expected in (
                ("logical_turn_count", count),
                ("provider_logical_call_count", count),
                (
                    "client_physical_dispatch_count",
                    sum(c["client_physical_dispatch_count"] for c in prefix),
                ),
                ("retrieval_round_count", max(0, count - 1)),
                ("fallback_count", 0),
                ("retry_count", 0),
            ):
                self.check(
                    type(counter.get(key)) is int and counter[key] == expected,
                    "INCOMPLETE_DISPATCH_SET",
                )

        if summary:
            counters(summary, len(calls), [b["resolved_input_binding_id"] for b in posts], calls)
        for i, post in enumerate(posts):
            counters(
                post["payload_snapshot"].get("interaction_counters", {}),
                i + 1,
                [b["resolved_input_binding_id"] for b in posts[:i]],
                calls[: i + 1],
            )
        for i, c in enumerate(calls):
            post = posts[i]
            pre_id = c.get("pre_call_B_ref")
            self.check(
                pre_id in ids and ids.index(pre_id) < ids.index(post["resolved_input_binding_id"]),
                "INCOMPLETE_DISPATCH_SET",
            )
            if i and pre_id in self.valid_bs:
                k = self.valid_bs[pre_id]["payload_snapshot"]["context_package"]
                previous = posts[i - 1]["payload_snapshot"]
                request = previous.get("response", {}).get("request")
                history = [sec for sec in k["sections"] if "prior_turn_receipt_ref" in sec]
                self.check(
                    len(history) == 1
                    and history[0].get("prior_turn_receipt_ref")
                    == posts[i - 1]["resolved_input_binding_id"]
                    and history[0].get("prior_context_id") == calls[i - 1]["context_id"]
                    and history[0].get("request") == request,
                    "INCOMPLETE_DISPATCH_SET",
                )
            v = self.call(c, post)
            if v:
                if any(
                    x["dispatch_id"] == v["dispatch_id"] or x["model_turn"] == v["model_turn"]
                    for x in self.out["dispatches"]
                ):
                    self.reasons.add("INCOMPLETE_DISPATCH_SET")
                else:
                    self.out["dispatches"].append(v)
        if not calls:
            for c in self.diagnostic_calls:
                v = self.call(c, None)
                if v and not any(
                    x["dispatch_id"] == v["dispatch_id"] for x in self.out["dispatches"]
                ):
                    self.out["dispatches"].append(v)
            self.reasons.add("INCOMPLETE_DISPATCH_SET")
        ds = self.out["dispatches"]
        if r:
            self.check(
                len(ds) == self.expected
                and [x["model_turn"] for x in ds] == list(range(1, len(ds) + 1))
                and [x["context_revision"] for x in ds] == list(range(1, len(ds) + 1)),
                "INCOMPLETE_DISPATCH_SET",
            )
            for m in r["output_records"]:
                self.material(m)
            snapshots = [m for m in r["output_records"] if m["kind"] == "TASK_OUTPUT_SNAPSHOT"]
            self.check(len(snapshots) == 1)
            if len(snapshots) == 1:
                m = snapshots[0]
                self.check(
                    m["record_id"] == m["content_digest"]
                    and m["payload_snapshot"]["resolved_inputs"] == ids
                    and m["payload_snapshot"]["admission_binding_id"] == a["admission_binding_id"]
                )
            outputs = [
                m
                for m in r["output_records"]
                if m["kind"] == "AGENT_OUTPUT"
                and m["payload_snapshot"].get("task_id") == self.task_id
            ]
            self.check(len(outputs) == 1)
            if len(outputs) == 1 and self.contexts:
                self.agent_output(outputs[0], self.contexts[-1]["context_id"])
        if self.contexts:
            last = self.contexts[-1]
            self.out["context_identity"] = dict(
                turns=self.contexts,
                final_context_id=last["context_id"],
                final_context_revision=last["context_revision"],
            )
        if r:
            self.out["result_identity"] = {
                **_pick(
                    r,
                    (
                        "result_id result_digest result_version status owner_generation "
                        "reservation_id admission_binding_id"
                    ),
                ),
                "ordered_B_ids": ids,
                "current_result_id": rid,
            }
        self.out["dependency_identity"] = list(self.dependencies.values())
        self.review_release()
        for cid, calc in self.methods.items():
            self.method(cid, calc)
        if r and self.contexts and not self.reasons.intersection(CORE_REASONS):
            last = self.contexts[-1]
            identity = dict(
                source_namespace=self.namespace,
                subject_type=SUBJECT,
                run_id=self.run_id,
                task_id=self.task_id,
                task_fingerprint=a["task_fingerprint"],
                graph=a["graph"],
                admission_binding_id=a["admission_binding_id"],
                ordered_B_ids=ids,
                result_id=rid,
                result_digest=r["result_digest"],
                result_version=r["result_version"],
                current_result_id=rid,
                final_context_id=last["context_id"],
                final_context_revision=last["context_revision"],
                final_context_manifest_digest=last["source_manifest_digest"],
                interaction_id=self.interaction,
                dispatch_membership=[
                    dict(
                        call_id=x["dispatch_id"],
                        pre_B_id=x["pre_B_id"],
                        receipt_B_id=x["receipt_B_id"],
                        context_id=x["context_id"],
                        context_revision=x["context_revision"],
                    )
                    for x in ds
                ],
            )
            self.out["subject_identity"] = identity
            self.out["subject_id"] = _hash(identity, "wp05-valuation-subject/v1")

    def agent_output(self, m, context_id):
        p = m["payload_snapshot"]
        self.check(
            p["run_id"] == self.run_id
            and p["actor"] == PROFILE[1]
            and p["status"] == "SUCCESS"
            and context_id in p["input_refs"]
        )
        self.check(p.get("structured_output") == getattr(self, "final_response", None))
        h = p["artifact_sha256"]
        blob = self.object("Blob", h)
        if blob is None:
            self.reasons.add("MISSING_CONTEXT_IDENTITY")
            return
        self.check(_raw(blob) == h)
        data = json.loads(blob)
        self.check(
            p["output_id"]
            == "AGOUT-"
            + str(uuid5(NAMESPACE_URL, f"{self.run_id}:{self.task_id}:{h.removeprefix('sha256:')}"))
        )
        for key in (
            "run_id",
            "task_id",
            "actor",
            "structured_output",
            "input_refs",
            "actual_model",
        ):
            self.check(data.get(key) == p.get(key))
        self.ref("Blob", h, blob)

    def review_release(self):
        review = self.object("Review", self.run_id)
        if review is None:
            self.reasons.add("MISSING_REVIEW")
        else:
            if type(review) is not dict:
                raise ValueError("review shape")
            # Check every supplied identity before classifying missing fields.
            for key in ("run_id", "review_id", "reviewer"):
                if review.get(key) is not None:
                    _shape(review[key], "id")
            if review.get("run_id") is not None:
                self.check(review["run_id"] == self.run_id)
            if review.get("status") is not None:
                _shape(review["status"], {"PASS", "BLOCK", "REVIEW"})
            for key in ("input_snapshot_hash", "record_digest", "requirement_context_digest"):
                if review.get(key) is not None:
                    _shape(review[key], "digest")
            if review.get("record_digest") is not None:
                self.check(
                    review["record_digest"]
                    == _hash(_without(review, "record_digest"), "wp05-source-object/v1")
                )
            if review.get("requirement_context_digest") is not None:
                self.check(
                    review["requirement_context_digest"] == _hash(review.get("requirement_context"))
                )
            if "source_namespace" in review:
                _shape(review["source_namespace"], NS_SHAPE)
                self.check(review["source_namespace"] == self.namespace)
            if "source_refs" in review:
                _shape(review["source_refs"], [REF_SHAPE])
                for ref in review["source_refs"]:
                    self.check(
                        ref["source_namespace"] == self.namespace
                        and ref["owner"] == "Review"
                        and ref["source_id"] == self.run_id
                    )
            subjects = []
            for key, values in review.items():
                if key.startswith("reviewed_") and key.endswith("_refs"):
                    _shape(values, ["id"])
                    subjects.extend(values)
            checks = review.get("checks", [])
            if type(checks) is not list:
                raise ValueError("review checks")
            projected_checks = []
            for c in checks:
                if type(c) is not dict or set(c) - {
                    "code",
                    "status",
                    "subject_refs",
                    "created_at",
                    "expected",
                    "actual",
                    "detail",
                }:
                    raise ValueError("review check fields")
                closed = _pick(c, "code status subject_refs")
                _shape(closed, CHECK_SHAPE)
                closed["subject_refs"] = sorted(set(closed["subject_refs"]))
                projected_checks.append(closed)
            if review.get("status") is not None:
                statuses = {c["status"] for c in projected_checks}
                self.check(
                    not ("BLOCK" in statuses and review["status"] != "BLOCK")
                    and not ("REVIEW" in statuses and review["status"] == "PASS")
                )
            required = ("run_id", "review_id", "reviewer", "status", "input_snapshot_hash")
            if any(review.get(k) is None for k in required) or not checks:
                self.reasons.add("MISSING_REVIEW")
            else:
                self.out["review_context"] = {
                    **_pick(review, "review_id run_id reviewer status input_snapshot_hash"),
                    "record_digest": _hash(review, "wp05-source-object/v1"),
                    "requirement_context_digest": _hash(review.get("requirement_context")),
                    "reviewed_subject_refs": sorted(set(subjects)),
                    "checks": projected_checks,
                    "scope": "RUN_CONTEXT_ONLY",
                    "source_refs": self.ref("Review", self.run_id, review),
                }
        release = self.object("Release", self.run_id)
        if release:
            for key in ("run_id", "result_id"):
                _shape(release.get(key), "id")
            _shape(release.get("canonical_record_id"), ("id",))
            self.check(release["run_id"] == self.run_id and self.run.get("status") == "RELEASED")
        self.out["release_context"] = dict(
            run_status=self.run.get("status"),
            released_result_id=release.get("result_id") if release else None,
            released_result_digest=_hash(release, "wp05-source-object/v1") if release else None,
            canonical_record_id=release.get("canonical_record_id") if release else None,
            scope="RUN_CONTEXT_ONLY",
            source_refs=self.ref("Release", self.run_id, release) if release else [],
        )

    def method(self, cid, core):
        package = self.object("Method", cid)
        if package is not None:
            if type(package) is not dict or set(package) != {"calculation", "entry"}:
                raise ValueError("method package")
            observations = package.get("entry", {}).get("observations", [])
            if type(observations) is not list:
                raise ValueError("method observations")
            # Even missing legacy metadata cannot hide a supplied foreign owner.
            for observation in observations:
                if type(observation) is not dict:
                    raise ValueError("method observation")
                for key, expected in (("run_id", self.run_id), ("task_id", core.get("task_id"))):
                    if observation.get(key) is not None:
                        _shape(observation[key], "id")
                        self.check(observation[key] == expected)
        meta = core.get("parameters", {}).get("wp04_method_binding")
        if not meta or not package:
            self.reasons.add("METHOD_IDENTITY_UNKNOWN")
            return
        calc, entry = package["calculation"], package["entry"]
        a, r = entry["A"], entry["R"]
        self.native(a, "admission_binding_id")
        self.native(r, "result_digest", "result_id")
        self.check(r["result_id"] == entry["current_result_id"] and not entry["invalidated"])
        self.check(
            any(
                m["record_id"] == cid and m["payload_snapshot"] == core for m in r["output_records"]
            )
        )
        descriptor, requirement, binding = (
            meta["descriptor"],
            meta["requirement"],
            meta["input_binding"],
        )
        self.check(
            meta == calc["parameters"]["wp04_method_binding"]
            and calc["calculation_id"] == cid
            and calc["run_id"] == self.run_id
            and meta["A_ref"] == a["admission_binding_id"]
        )
        self.check(
            descriptor["source_manifest_digest"]
            == _hash(descriptor["source_manifest"], "wp04-source-manifest/v1")
        )
        source = next(
            (
                x["sha256"]
                for x in descriptor["source_manifest"]
                if x["path"] == "src/capabilities/financial/growth.py"
            ),
            None,
        )
        self.check(source == core["implementation_hash"] == calc["implementation_hash"])
        self.check(
            all(calc.get(k) == v for k, v in core.items() if k != "implementation_identity_source")
        )
        self.check(
            requirement["descriptor"] == descriptor
            and requirement["run_id"] == calc["run_id"]
            and requirement["task_id"] == calc["task_id"]
            and requirement["requirement_digest"] == binding["requirement_digest"]
        )
        self.check(
            descriptor["descriptor_digest"]
            == _hash(_without(descriptor, "descriptor_digest"), descriptor["method_schema_version"])
        )
        self.check(
            requirement["requirement_id"]
            == requirement["requirement_digest"]
            == _hash(
                _without(requirement, "requirement_id", "requirement_digest"),
                requirement["schema_version"],
            )
        )
        self.check(
            binding["input_identity_digest"]
            == _hash(_without(binding, "input_identity_digest"), "wp04-input-binding/v1")
        )
        bs = [b for b in entry["B"] if b["resolved_input_binding_id"] == meta["B_ref"]]
        if not self.check(len(bs) == 1):
            return
        b = bs[0]
        self.native(b, "resolved_input_binding_id")
        self.check(
            b["input_digest"] == _hash(b["payload_snapshot"], "wp02-input-payload/v1")
            and b["resolved_input_binding_id"] in r["resolved_input_binding_ids"]
            and all(meta.get(k) == v for k, v in b["payload_snapshot"]["wp04"].items())
        )
        # Close the selected producer, not the consuming valuation task. The
        # producer R must be exactly the dependency already selected by K/B/A.
        self.check(
            self.root["results"].get(r["result_id"]) == r
            and self.root["current_results"].get(calc["task_id"]) == r["result_id"]
            and any(d["result_id"] == r["result_id"] for d in self.a["dependency_result_bindings"])
        )
        producer = self.root["attempts"].get(calc["task_id"], {}).get("admission")
        self.check(producer == a and entry["task"] == a["authorized_input_requirements"]["task"])
        self.check(
            a["run_id"] == r["run_id"] == requirement["run_id"] == binding["run_id"] == self.run_id
            and a["task_id"]
            == r["producer_task_id"]
            == requirement["task_id"]
            == binding["task_id"]
            == calc["task_id"]
            and a["object_id"]
            == requirement["object_id"]
            == binding["object_id"]
            == self.a["object_id"]
            and requirement == entry["task"].get("wp04_method_requirement")
            and requirement["scheme_id"] == a["scheme_id"]
            and requirement["scheme_hash"] == a["scheme_hash"]
            and b["admission_binding_id"] == r["admission_binding_id"] == a["admission_binding_id"]
            and b["reservation_id"] == r["reservation_id"] == a["attempt_reservation_id"]
            and r["graph"] == a["graph"] == self.a["graph"]
            and r["task_fingerprint"] == a["task_fingerprint"]
            and r["owner_generation"] == a["owner"]["owner_generation"]
        )
        observations = entry["observations"]
        observation_fields = set(
            (
                "schema_version observation_id run_id object_id task_id owner_id "
                "owner_generation task_fingerprint requirement_id requirement_digest "
                "requirement_state descriptor descriptor_digest input_binding "
                "input_identity_digest observed_input_refs missing_fields "
                "verification_state admission_binding_id reservation_id B_ref phase "
                "support_status diagnostic_code numeric_outcome calculation_ref "
                "source_manifest_digest semantic_policy_digest decimal_policy_digest "
                "dispatch_count previous_observation_id observed_at audit_duration_ms "
                "authority_status"
            ).split()
        )
        for o in observations:
            if type(o) is not dict or set(o) != observation_fields:
                raise ValueError("MethodObservation shape")
            self.check(
                o["observation_id"] == _hash(_without(o, "observation_id"), o["schema_version"])
            )
            expected = dict(
                schema_version="wp04-method-observation/v1",
                run_id=self.run_id,
                object_id=a["object_id"],
                task_id=calc["task_id"],
                owner_id=a["owner"]["owner_id"],
                owner_generation=a["owner"]["owner_generation"],
                task_fingerprint=a["task_fingerprint"],
                requirement_id=requirement["requirement_id"],
                requirement_digest=requirement["requirement_digest"],
                requirement_state=requirement["requirement_state"],
                descriptor=descriptor,
                descriptor_digest=descriptor["descriptor_digest"],
                input_binding=binding,
                input_identity_digest=binding["input_identity_digest"],
                admission_binding_id=a["admission_binding_id"],
                reservation_id=a["attempt_reservation_id"],
                support_status="SUPPORTED",
                diagnostic_code="NONE",
                verification_state="VERIFIED",
                missing_fields=[],
                authority_status="COMMITTED",
                source_manifest_digest=descriptor["source_manifest_digest"],
                semantic_policy_digest=descriptor["semantic_policy_digest"],
                decimal_policy_digest=descriptor["decimal_policy_digest"],
            )
            self.check(
                all(
                    o.get(k) == value and type(o.get(k)) is type(value)
                    for k, value in expected.items()
                )
            )
            _shape(o.get("observed_input_refs"), ["id"])
            self.check(set(binding["input_evidence_ids"]).issubset(o["observed_input_refs"]))
            if o.get("phase") == "PREPARED":
                self.check(
                    o.get("B_ref") is None
                    and o.get("calculation_ref") is None
                    and o.get("previous_observation_id") is None
                    and o.get("numeric_outcome") == "NONE"
                    and type(o.get("dispatch_count")) is int
                    and o["dispatch_count"] == 0
                )
            else:
                self.check(
                    o.get("phase") == "EXECUTION_FINISHED"
                    and o.get("B_ref") == meta["B_ref"]
                    and o.get("calculation_ref") == cid
                    and o.get("numeric_outcome") == "SUCCEEDED"
                    and type(o.get("dispatch_count")) is int
                    and o["dispatch_count"] == 1
                )
        finished = [
            o
            for o in observations
            if o.get("calculation_ref") == cid and o["numeric_outcome"] == "SUCCEEDED"
        ]
        self.check(len(finished) == 1)
        prepared = [
            o
            for o in observations
            if o["observation_id"] == meta["prepared_observation_ref"] and o["phase"] == "PREPARED"
        ]
        self.check(len(prepared) == 1 and len(finished) == 1)
        if finished and prepared:
            self.check(
                finished[0]["previous_observation_id"] == prepared[0]["observation_id"]
                and finished[0]["B_ref"] == meta["B_ref"]
                and finished[0]["descriptor_digest"] == descriptor["descriptor_digest"]
            )
        self.check(binding["input_evidence_ids"] == calc["input_evidence_ids"])
        for eid, edigest in zip(
            binding["input_evidence_ids"], binding["evidence_digests"], strict=True
        ):
            candidate = next(
                (
                    c
                    for c in a["authorized_input_requirements"]["wp04_candidates"]
                    if c["evidence_id"] == eid
                ),
                None,
            )
            self.check(candidate is not None and candidate["content_digest"] == edigest)
            if candidate:
                self.check(_hash(candidate["snapshot"], "evidence-record/v1") == edigest)
        flags = meta["decimal_flags_observation"]
        self.check(
            flags.get("schema_version") == "wp04-revenue-growth-decimal-observation/v1"
            and type(flags.get("capture_count")) is int
            and flags["capture_count"] == 1
            and set(flags.get("flags", {}))
            == {
                "Clamped",
                "DivisionByZero",
                "FloatOperation",
                "Inexact",
                "InvalidOperation",
                "Overflow",
                "Rounded",
                "Subnormal",
                "Underflow",
            }
            and all(type(v) is bool for v in flags.get("flags", {}).values())
            and flags["flags"] == meta["resulting_decimal_flags"]
        )
        self.check(
            meta["formula_version"] == descriptor["formula_version"] == "1.0.0"
            and descriptor["capability_id"] == core["capability_id"] == "revenue_growth"
            and descriptor["capability_version"] == core["capability_version"] == "1.1.0"
            and meta["dispatch_count"] == 1
            and meta["support_status"] == "SUPPORTED"
        )
        self.out["method_dependency_context"].append(
            dict(
                calculation_id=cid,
                applicability="APPLICABLE",
                **_pick(
                    descriptor,
                    (
                        "capability_id capability_version formula_id formula_version "
                        "descriptor_digest source_manifest_digest semantic_policy_digest "
                        "decimal_policy_digest"
                    ),
                ),
                implementation_hash=core["implementation_hash"],
                input_identity_digest=binding["input_identity_digest"],
                requirement_id=requirement["requirement_id"],
                B_ref=meta["B_ref"],
                observation_id=finished[0]["observation_id"] if finished else None,
                support_status=meta["support_status"],
                diagnostic_code=finished[0]["diagnostic_code"] if finished else None,
                numeric_outcome=finished[0]["numeric_outcome"] if finished else None,
                actual_flags_digest=_hash(flags, "wp05-actual-flags-ref/v1"),
                source_refs=self.ref("Method", cid, package),
            )
        )

    def finish(self):
        complete = not self.reasons.intersection(CORE_REASONS) and not self.legacy
        ds = self.out["dispatches"]
        expected = getattr(self, "expected", None)
        aggregate = {"membership_complete": complete}
        for metric in METRICS:
            known = [d[metric] for d in ds if d[metric]["value"] is not None]
            refs = [ref for v in known for ref in v["source_refs"]]
            subtotal = (
                _known(
                    sum(x["value"] for x in known),
                    "DERIVED_FROM_OBSERVED",
                    refs,
                    "SUM_MODEL_TURN_ELAPSED"
                    if metric == "model_turn_elapsed"
                    else "WP05_SUM_EXACT_DISPATCH_FIELD_V1",
                )
                if known
                else _unknown()
            )
            covered = complete and type(expected) is int and expected > 0 and len(known) == expected
            aggregate[metric] = dict(
                expected_dispatch_count=expected,
                observed_metric_count=len(known),
                complete_for_metric=covered,
                observed_subtotal=subtotal,
                complete_total=subtotal if covered else _unknown("INCOMPLETE_MEMBERSHIP"),
                unknown_dispatch_ids=[d["dispatch_id"] for d in ds if d[metric]["value"] is None],
            )
        self.out["usage_aggregate"] = aggregate
        if self.reasons.intersection(CORE_REASONS):
            state = "NOT_READY"
            self.out["subject_id"] = self.out["subject_identity"] = None
        elif self.legacy:
            state = "LEGACY_UNKNOWN"
            self.reasons.add("LEGACY_METADATA_ABSENT")
        else:
            state = "PARTIALLY_READY" if self.reasons else "READY"
        self.out["readiness_state"], self.out["readiness_reasons"] = state, sorted(self.reasons)
        self.out["safe_source_manifest"] = sorted(
            {_json(r): r for r in self.manifest}.values(),
            key=lambda r: (
                _json(r["source_namespace"]),
                r["owner"],
                r["source_id"],
                r["content_digest"],
                r["field_selectors"],
            ),
        )
        self.out["dependency_identity"].sort(key=lambda r: (r["owner"], r["source_id"]))
        self.out["method_dependency_context"].sort(key=lambda r: r["calculation_id"])

        try:
            _export_shape(self.out)
        except (ValueError, TypeError, KeyError):
            return _error_envelope("IDENTITY_MISMATCH")
        self.out["envelope_digest"] = _hash(_without(self.out, "envelope_digest"), SCHEMA)
        return self.out


def _error_envelope(reason):
    p = _Projection()
    p.reasons.add(reason)
    return p.finish()


def build_evaluation_input(
    snapshot_before, snapshot_after, subject_selector
) -> EvaluationInputEnvelope:
    """Pure two-checkpoint projection. Unknown values are explicit EvidenceValues.

    Integrity failure is a safe NOT_READY diagnostic; no caller objects are invoked.
    Static fixture checkpoints assert retained-snapshot currentness only.
    """
    p = _Projection()
    try:
        _plain(snapshot_before)
        _plain(snapshot_after)
        _plain(subject_selector)
        before_text = _json(snapshot_before)
        before = json.loads(before_text)
        if snapshot_after is None:
            p.reasons.add("STALE_SOURCE")
        else:
            after = json.loads(_json(snapshot_after))
            q = _Projection()
            q.load(after, subject_selector)
            if q.reasons or before != after:
                p.reasons.add("STALE_SOURCE")
        if p.load(before, subject_selector):
            p.core()
        p.check(_json(before) == before_text, "STALE_SOURCE")
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError):
        p.reasons.add("IDENTITY_MISMATCH")
    return p.finish()
