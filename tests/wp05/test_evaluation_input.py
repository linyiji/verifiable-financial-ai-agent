"""T01–T36. Fresh real bounded WP03 calls via MockTransport; pure projection tests.

Synthetic detached Review/Release context is never production assurance evidence.
All mutation cases modify private NEW fixture copies; retained bytes never change.
"""

import asyncio
import builtins
import hashlib
import json
import os
import socket
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from src.application.evaluation_input import build_evaluation_input
from src.domain.node_binding import canonical_value, digest
from tests.wp03 import test_valuation_retrieval as wp03

SPEC = json.loads((Path(__file__).parent / "fixtures/evaluation_input_cases.json").read_text())
BASELINE = "e290403578cd5485bcee53649ae14f835905d484"


def sha(text):
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def record(owner, sid, payload, scope="DETACHED_OWNER_SNAPSHOT"):
    return dict(
        owner=owner,
        source_id=sid,
        payload=payload,
        content_digest=digest(payload, "wp05-source-object/v1"),
        evidence_scope=scope,
    )


def seal(snapshot):
    for r in snapshot["records"]:
        r["content_digest"] = digest(r["payload"], "wp05-source-object/v1")
    if snapshot["source_namespace"]["kind"] == "DETACHED_OWNER_SNAPSHOT":
        members = sorted(
            [
                {k: r[k] for k in ("owner", "source_id", "content_digest")}
                for r in snapshot["records"]
            ],
            key=lambda r: (r["owner"], r["source_id"], r["content_digest"]),
        )
        snapshot["source_namespace"]["anchor_digest"] = digest(members, "wp05-source-bundle/v1")
    return snapshot


def obj(s, owner):
    return next(r["payload"] for r in s["records"] if r["owner"] == owner)


def selector(s):
    root = (
        obj(s, "Repository")
        if s["source_namespace"]["kind"] == "DETACHED_OWNER_SNAPSHOT"
        else json.loads(s["retained_json"])["root"]
    )
    task = next(
        k
        for k, v in root["attempts"].items()
        if v["admission"]["authorized_input_requirements"]["task"]["task_type"]
        == "valuation_analysis"
    )
    return dict(
        run_id=root["run_id"], task_id=task, source_namespace=deepcopy(s["source_namespace"])
    )


def project(s, after=True):
    return build_evaluation_input(s, deepcopy(s) if after is True else after, selector(s))


def current(s):
    root = obj(s, "Repository")
    tid = selector(s)["task_id"]
    return root, root["results"][root["current_results"][tid]]


def posts(s):
    root, r = current(s)
    return [
        root["resolved_inputs"][bid]
        for bid in r["resolved_input_binding_ids"]
        if root["resolved_inputs"][bid]["step_id"].endswith(":receipt")
    ]


def change_receipt(s, index, **changes):
    """Construct an internally coherent synthetic metadata variant, not runtime history."""
    root, r = current(s)
    b = posts(s)[index]
    old_b = b["resolved_input_binding_id"]
    c = b["payload_snapshot"]["execution_receipt"]
    c.update(changes)
    b["payload_snapshot"]["interaction_counters"]["calls"][index].update(changes)
    b["input_digest"] = digest(b["payload_snapshot"], "wp02-input-payload/v1")
    b["resolved_input_binding_id"] = digest(
        {k: v for k, v in b.items() if k != "resolved_input_binding_id"}, b["schema_version"]
    )
    root["resolved_inputs"].pop(old_b)
    root["resolved_inputs"][b["resolved_input_binding_id"]] = b
    r["resolved_input_binding_ids"] = [
        b["resolved_input_binding_id"] if x == old_b else x for x in r["resolved_input_binding_ids"]
    ]
    su = r["observed_execution"]["wp03_context"]
    su["calls"][index].update(changes)
    su["receipt_refs"][index] = b["resolved_input_binding_id"]
    resign_result(s)


def resign_result(s):
    root, r = current(s)
    old = r["result_id"]
    for m in r["output_records"]:
        if m["kind"] == "TASK_OUTPUT_SNAPSHOT":
            m["payload_snapshot"]["resolved_inputs"] = list(r["resolved_input_binding_ids"])
            m["record_id"] = m["content_digest"] = digest(m["payload_snapshot"], m["record_schema"])
    new = digest(
        {k: v for k, v in r.items() if k not in ("result_id", "result_digest")}, r["schema_version"]
    )
    r["result_id"] = r["result_digest"] = new
    root["results"].pop(old)
    root["results"][new] = r
    root["current_results"][r["producer_task_id"]] = new
    seal(s)


def add_blobs(records, root):
    added = set()
    for b in root["resolved_inputs"].values():
        for m in b["material_refs"]:
            if m["kind"] in ("EVIDENCE", "AGENT_OUTPUT"):
                text = Path(m["location"]).read_text()
                if sha(text) not in added:
                    records.append(record("Blob", sha(text), text, "RETAINED_LOCAL_FIXTURE"))
                    added.add(sha(text))
    for r in root["results"].values():
        for m in r["output_records"]:
            if m["kind"] == "AGENT_OUTPUT":
                text = Path(m["location"]).read_text()
                if sha(text) not in added:
                    records.append(record("Blob", sha(text), text, "RETAINED_LOCAL_FIXTURE"))
                    added.add(sha(text))


async def generate(tmp, mode="final", usage=None, method=False):
    tmp.mkdir(parents=True)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            socket.socket, "connect", Mock(side_effect=AssertionError("live network forbidden"))
        )
        original_response = httpx.Response
        count = 0

        def response(*args, **kwargs):
            nonlocal count
            body = kwargs.get("json")
            if isinstance(body, dict) and "choices" in body and usage is not None:
                i, o = usage[count]
                count += 1
                kwargs["json"] = {**body, "usage": {"prompt_tokens": i, "completion_tokens": o}}
            return original_response(*args, **kwargs)

        mp.setattr(httpx, "Response", response)
        holder = {}
        if method:
            from tests.wp04.test_method_binding import setup

            async def wired(path):
                service, value = await setup(path, extra_tasks=True)
                from src.agentic.research_agent import LLMResearchAgent
                from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore

                service.agent_registry.register(
                    LLMResearchAgent(
                        agent_id="valuation_analyst",
                        supported_task_types=("valuation_analysis",),
                        provider=None,
                        artifacts=ResearchAgentOutputArtifactStore(path / "valuation-artifacts"),
                    )
                )
                from tests.wp02.test_node_binding import FakeLLM

                service.agent_registry.register(
                    LLMResearchAgent(
                        agent_id="fundamental_analyst",
                        supported_task_types=("fundamental_analysis",),
                        provider=FakeLLM(service.repository),
                        artifacts=ResearchAgentOutputArtifactStore(path / "fundamental-artifacts"),
                    )
                )
                holder["service"] = service
                return service, value, None, None

            mp.setattr(wp03, "wired", wired)
        result, calls, receipts, task = await wp03.run_case(tmp, mp, mode)
        root = canonical_value(result.node_binding)
        records = [
            record("Repository", root["run_id"], root, "RETAINED_LOCAL_FIXTURE"),
            record(
                "Application", root["run_id"], canonical_value(result.run), "RETAINED_LOCAL_FIXTURE"
            ),
        ]
        add_blobs(records, root)
        review = dict(
            review_id="REVIEW-WP05-LOCAL",
            run_id=root["run_id"],
            reviewer="independent-financial-review-v2",
            status="BLOCK",
            input_snapshot_hash=digest({"fixture": "explicit synthetic Review context"}),
            requirement_context=None,
            reviewed_calculation_refs=[],
            reviewed_evidence_refs=[],
            checks=[dict(code="FIN_LOCAL_CONTEXT", status="BLOCK", subject_refs=[])],
        )
        records.append(record("Review", root["run_id"], review, "SYNTHETIC_CONTEXT"))
        if method:
            ctx = holder["service"]._wp04_context(result)
            for calc in result.artifacts.calculations:
                if "wp04_method_binding" in calc.parameters:
                    records.append(
                        record(
                            "Method",
                            calc.calculation_id,
                            dict(calculation=canonical_value(calc), entry=ctx["entries"][0]),
                            "RETAINED_LOCAL_FIXTURE",
                        )
                    )
        s = seal(
            dict(
                source_namespace=dict(kind="DETACHED_OWNER_SNAPSHOT", anchor_digest=""),
                records=records,
            )
        )
        assert len(calls) == len(receipts)
        if usage is not None:
            assert [(c["input_tokens"], c["output_tokens"]) for c in receipts] == [
                tuple(x) for x in usage
            ]
            assert all(type(c["elapsed_ms"]) is int for c in receipts)
        return s


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("wp05-inputs")
    values = {}
    for key in ("F_READY_ONE", "F_READY_TWO"):
        spec = SPEC[key]
        values[key] = asyncio.run(generate(tmp / key, spec["mode"], spec["usage"]))
    for mode in ("timeout", "cancel"):
        values[mode] = asyncio.run(generate(tmp / mode, mode))
    values["zero_two"] = asyncio.run(
        generate(tmp / "reported-zero-two", "retrieve", usage=[[0, 0], [0, 0]])
    )
    values["zero"] = asyncio.run(generate(tmp / "reported-zero", usage=[[0, 0]]))
    values["method"] = asyncio.run(generate(tmp / "method", usage=[[100, 20]], method=True))
    # Retained files are loaded without altering their original serialization.
    for name, expected in SPEC["retained"].items():
        path = Path(SPEC["retained_directory"]) / name
        text = path.read_text()
        assert sha(text) == "sha256:" + expected
        doc = json.loads(text)
        blobs = []
        for path in set(doc["retained_source_files"].values()):
            data = Path(path).read_text()
            blobs.append(record("Blob", sha(data), data, "RETAINED_LOCAL_FIXTURE"))
        values[name] = dict(
            source_namespace=dict(kind="RETAINED_LOCAL_FIXTURE", anchor_digest=sha(text)),
            retained_json=text,
            records=blobs,
        )
    destination = os.environ.get("WP05_EVIDENCE_DIR")
    if destination:
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        for name, value in values.items():
            (target / (name + ".snapshot.json")).write_text(
                json.dumps(value, ensure_ascii=False, indent=2)
            )
            (target / (name + ".envelope.json")).write_text(
                json.dumps(project(value), ensure_ascii=False, indent=2)
            )
    return values


def metric(e, name="input_tokens"):
    return e["usage_aggregate"][name]


def expect(e, state, reason=None):
    assert e["readiness_state"] == state, e["readiness_reasons"]
    if reason:
        assert reason in e["readiness_reasons"]
    assert e["readiness_reasons"] == sorted(set(e["readiness_reasons"]))
    if state == "NOT_READY":
        assert e["subject_id"] is None


@pytest.mark.parametrize("scenario", [f"T{i:02}" for i in range(1, 37)])
def test_contract(scenario, fixtures, monkeypatch):
    s = deepcopy(fixtures["F_READY_TWO" if scenario in ("T02", "T11", "T22") else "F_READY_ONE"])
    if scenario in ("T01", "T02", "T03"):
        e = project(s)
        expect(e, "READY")
        assert metric(e)["complete_total"]["value"] == (180 if scenario == "T02" else 100)
        assert e["review_context"]["status"] == "BLOCK"
    elif scenario == "T04":
        released_context(s)
        e = project(s)
        expect(e, "READY")
        assert e["release_context"]["run_status"] == "RELEASED"
        assert e["release_context"]["released_result_id"] == "RELEASE-LOCAL"
        assert e["release_context"]["canonical_record_id"] == "CER-LOCAL"
        assert e["release_context"]["released_result_digest"] == digest(
            obj(s, "Release"), "wp05-source-object/v1"
        )
    elif scenario == "T05":
        for name in SPEC["retained"]:
            e = project(deepcopy(fixtures[name]))
            expect(e, "PARTIALLY_READY", "MISSING_USAGE_PROVENANCE")
            assert metric(e)["complete_total"]["value"] is None
    elif scenario == "T06":
        s["records"] = [r for r in s["records"] if r["owner"] != "Review"]
        seal(s)
        expect(project(s), "PARTIALLY_READY", "MISSING_REVIEW")
    elif scenario in ("T07", "T24"):
        change_receipt(s, 0, observed_model="UNKNOWN", model_identity_source="UNKNOWN")
        e = project(s)
        expect(e, "PARTIALLY_READY", "MISSING_MODEL_OBSERVATION")
        assert e["dispatches"][0]["observed_model"]["value"] is None
        assert e["dispatches"][0]["requested_model"]["value"] == "gpt-5.6-sol"
    elif scenario == "T08":
        root, r = current(s)
        root["results"].pop(r["result_id"])
        root["current_results"].pop(r["producer_task_id"])
        seal(s)
        e = project(s)
        expect(e, "NOT_READY", "MISSING_RESULT_BINDING")
        assert len(e["dispatches"]) == 1
    elif scenario == "T09":
        root, r = current(s)
        root["current_results"][r["producer_task_id"]] = "sha256:" + "0" * 64
        seal(s)
        expect(project(s), "NOT_READY", "STALE_RESULT_POINTER")
    elif scenario == "T10":
        root, r = current(s)
        r["task_fingerprint"] = "sha256:" + "0" * 64
        resign_result(s)
        expect(project(s), "NOT_READY", "IDENTITY_MISMATCH")
    elif scenario in ("T11", "T23"):
        root, r = current(s)
        bid = posts(s)[-1]["resolved_input_binding_id"]
        root["resolved_inputs"].pop(bid)
        seal(s)
        e = project(s)
        expect(e, "NOT_READY", "INCOMPLETE_DISPATCH_SET")
        assert metric(e)["complete_total"]["value"] is None
    elif scenario == "T12":
        root, r = current(s)
        r["resolved_input_binding_ids"].append(r["resolved_input_binding_ids"][-1])
        resign_result(s)
        expect(project(s), "NOT_READY", "INCOMPLETE_DISPATCH_SET")
        for name in (
            "B03_turn_conflict",
            "B03_pre_B_conflict",
            "B03_post_counter_conflict",
            "B03_post_receipt_ref_conflict",
        ):
            assert_blocker(name, fixtures)
    elif scenario == "T13":
        root, r = current(s)
        b = posts(s)[0]
        b["payload_snapshot"]["execution_receipt"]["context_id"] = "sha256:" + "0" * 64
        seal(s)
        expect(project(s), "NOT_READY", "IDENTITY_MISMATCH")
    elif scenario == "T14":
        run = obj(s, "Application")
        rid = run["run_id"]
        s["records"] = [record("Application", rid, run)]
        seal(s)
        sel = dict(run_id=rid, task_id=rid + ":1", source_namespace=s["source_namespace"])
        expect(build_evaluation_input(s, s, sel), "LEGACY_UNKNOWN", "LEGACY_METADATA_ABSENT")
    elif scenario in ("T15", "T16", "T17"):
        e = project(deepcopy(fixtures["cancel" if scenario == "T16" else "timeout"]))
        expect(e, "NOT_READY", "MISSING_RESULT_BINDING")
        assert len(e["dispatches"]) == 1
        assert e["dispatches"][0]["status"] == "RESULT_UNKNOWN"
        assert e["dispatches"][0]["physical_dispatch_count"]["value"] == 1
        assert e["dispatches"][0]["model_turn_elapsed"]["value"] is not None
        if scenario == "T17":
            change_receipt(s, 0, phase="FAILED", diagnostic_code="CancelledError")
            root, r = current(s)
            root["current_results"].pop(r["producer_task_id"])
            root["results"].pop(r["result_id"])
            seal(s)
            observed = project(s)
            expect(observed, "NOT_READY")
            assert observed["dispatches"][0]["input_tokens"]["value"] == 100
            assert metric(observed)["observed_subtotal"]["value"] == 100
            assert metric(observed)["complete_total"]["value"] is None
    elif scenario == "T18":
        s = deepcopy(fixtures["zero"])
        e = project(s)
        expect(e, "READY")
        assert metric(e)["complete_total"]["value"] == 0
        assert e["dispatches"][0]["model_turn_elapsed"]["value"] >= 0
        for v in (True, -1):
            bad = deepcopy(s)
            change_receipt(bad, 0, input_tokens=v)
            expect(project(bad), "NOT_READY", "USAGE_IDENTITY_MISMATCH")
        for name in ("B03_wrong_receipt_schema", "B03_unproven_receipt_zero"):
            assert_blocker(name, fixtures)
        expect(project(deepcopy(fixtures["zero_two"])), "READY")
        assert metric(project(fixtures["zero_two"]))["complete_total"]["value"] == 0
    elif scenario in ("T19", "T20", "T21"):
        e = project(s)
        expect(e, "READY")
        fields = {
            "T19": ["cached_input_tokens", "reasoning_output_tokens"],
            "T20": ["cost"],
            "T21": ["provider_only_latency"],
        }[scenario]
        for field in fields:
            assert e["dispatches"][0][field]["value"] is None
            assert metric(e, field)["complete_total"]["value"] is None
        assert e["dispatches"][0]["model_turn_elapsed"]["provenance"] == "RUNTIME_MEASUREMENT"
        assert e["dispatches"][0]["model_turn_elapsed"]["derivation_rule"] == "MODEL_TURN_ELAPSED"
    elif scenario == "T22":
        change_receipt(s, 1, input_tokens=None)
        e = project(s)
        expect(e, "PARTIALLY_READY")
        m = metric(e)
        assert (
            m["expected_dispatch_count"],
            m["observed_metric_count"],
            m["observed_subtotal"]["value"],
            m["complete_total"]["value"],
        ) == (2, 1, 100, None)
    elif scenario in ("T25", "T26"):
        s = deepcopy(fixtures["method"])
        if scenario == "T26":
            package = obj(s, "Method")
            package["calculation"]["parameters"]["wp04_method_binding"]["formula_version"] = "bad"
            seal(s)
            expect(project(s), "NOT_READY", "IDENTITY_MISMATCH")
        else:
            e = project(s)
            # The actual valuation also selected legacy EBITDA. Its missing version
            # remains partial; exact revenue-growth metadata is still projected.
            expect(e, "PARTIALLY_READY", "METHOD_IDENTITY_UNKNOWN")
            assert e["method_dependency_context"][0]["capability_id"] == "revenue_growth"
            assert e["method_dependency_context"][0]["actual_flags_digest"]
            absent = deepcopy(s)
            absent["records"] = [r for r in absent["records"] if r["owner"] != "Method"]
            seal(absent)
            expect(project(absent), "PARTIALLY_READY", "METHOD_IDENTITY_UNKNOWN")
            unselected = deepcopy(s)
            unselected["records"].append(
                record(
                    "Method", "CALC-UNSELECTED", {"do_not_scan": "arbitrary"}, "SYNTHETIC_CONTEXT"
                )
            )
            seal(unselected)
            e2 = project(unselected)
            assert e2["readiness_state"] == e["readiness_state"]
            assert all(
                x["calculation_id"] != "CALC-UNSELECTED" for x in e2["method_dependency_context"]
            )
        assert_blocker(
            "B05_cross_run_method_observation"
            if scenario == "T25"
            else "B05_wrong_selected_source",
            fixtures,
        )
    elif scenario == "T27":
        e = project(s)
        text = json.dumps(e)
        for forbidden in (
            "/private/",
            "https://",
            "FAKE_LOCAL_ONLY",
            "sections",
            "structured_output",
        ):
            assert forbidden not in text

        def assert_no_private_objects(value):
            if isinstance(value, dict):
                assert not {"configuration_snapshot", "sections", "structured_output"}.intersection(
                    value
                )
                for child in value.values():
                    assert_no_private_objects(child)
            elif isinstance(value, list):
                for child in value:
                    assert_no_private_objects(child)

        assert_no_private_objects(e)
        for name in SPEC["remediation_cases"]:
            if name.startswith("B02_"):
                assert_blocker(name, fixtures)
        assert set(e) == set(
            (
                "schema_version readiness_policy_id subject_type subject_id "
                "subject_identity task_identity graph_identity result_identity "
                "context_identity dependency_identity dispatches usage_aggregate "
                "review_context release_context method_dependency_context "
                "readiness_state readiness_reasons safe_source_manifest envelope_digest"
            ).split()
        )
    elif scenario == "T28":
        before = deepcopy(s)
        a = deepcopy(s)
        project(s, a)
        assert s == before == a
    elif scenario == "T29":
        sel = selector(s)
        after = deepcopy(s)
        forbidden = Mock(side_effect=AssertionError("builder I/O"))
        monkeypatch.setattr(builtins, "open", forbidden)
        monkeypatch.setattr(Path, "open", forbidden)
        monkeypatch.setattr(socket.socket, "connect", forbidden)
        monkeypatch.setattr(httpx.AsyncClient, "post", forbidden)
        from src.application.repository import InMemoryApplicationRepository
        from src.assurance.independent_financial_review import IndependentFinancialReviewer
        from src.assurance.release_gate import ReleaseGate
        from src.infrastructure.database.research_memory import ResearchMemoryRepository
        from src.observability.performance import Recorder

        for cls, name in [
            (InMemoryApplicationRepository, "get_run_fresh"),
            (InMemoryApplicationRepository, "commit_node_result"),
            (IndependentFinancialReviewer, "review"),
            (ReleaseGate, "evaluate"),
            (ResearchMemoryRepository, "read_exact"),
        ]:
            monkeypatch.setattr(cls, name, forbidden)
        for name in ("record", "flush"):
            if hasattr(Recorder, name):
                monkeypatch.setattr(Recorder, name, forbidden)
        # Runtime imports above are setup, not inside the pure call.
        with monkeypatch.context() as guard:
            guard.setattr(os, "getenv", forbidden)
            guard.setattr(os, "open", forbidden)
            guard.setattr(socket, "create_connection", forbidden)
            e = build_evaluation_input(s, after, sel)
        expect(e, "READY")
        forbidden.assert_not_called()
    elif scenario == "T30":
        sel = selector(s)
        other = deepcopy(s)
        obj(other, "Review")["review_id"] = "REVIEW-DIFFERENT"
        seal(other)
        expect(build_evaluation_input(other, other, sel), "NOT_READY", "IDENTITY_MISMATCH")
    elif scenario == "T31":
        a = deepcopy(s)
        obj(a, "Review")["status"] = "PASS"
        seal(a)
        expect(project(s, a), "NOT_READY", "STALE_SOURCE")
        expect(project(s, None), "NOT_READY", "STALE_SOURCE")
    elif scenario == "T32":
        e = project(s)
        assert e["envelope_digest"] == digest(
            {k: v for k, v in e.items() if k != "envelope_digest"}, "vefin-evaluation-input/v1"
        )
        reordered = json.loads(json.dumps(s, sort_keys=True))
        assert project(reordered) == e
        change_receipt(s, 0, input_tokens=101)
        assert project(s)["envelope_digest"] != e["envelope_digest"]
        # Independent canonical encoder and pinned Unicode/null/order golden vector.
        vector = SPEC["canonical_vector"]
        assert independent_digest(vector["value"], vector["schema"]) == vector["digest"]
        assert (
            independent_digest(
                {k: v for k, v in e.items() if k != "envelope_digest"}, "vefin-evaluation-input/v1"
            )
            == e["envelope_digest"]
        )
        base = project(fixtures["F_READY_TWO"])
        for edit in (
            lambda x: x["result_identity"]["ordered_B_ids"].reverse(),
            lambda x: x["dispatches"].reverse(),
            lambda x: x.update(readiness_state="PARTIALLY_READY"),
            lambda x: x["dispatches"][0]["input_tokens"].update(provenance="UNKNOWN"),
        ):
            candidate = deepcopy(base)
            edit(candidate)
            assert (
                independent_digest(
                    {k: v for k, v in candidate.items() if k != "envelope_digest"},
                    "vefin-evaluation-input/v1",
                )
                != base["envelope_digest"]
            )
        stamped = deepcopy(fixtures["F_READY_TWO"])
        stamped["export_timestamp"] = "2099-01-01T00:00:00Z"
        assert project(stamped) == base
    elif scenario == "T33":
        root, r = current(s)
        root["current_results"].pop(r["producer_task_id"])
        root["results"].pop(r["result_id"])
        for b in posts_from_root(root):
            root["resolved_inputs"].pop(b["resolved_input_binding_id"])
        seal(s)
        e = project(s)
        expect(e, "NOT_READY")
        assert metric(e)["complete_total"]["value"] is None
        # A loose retained diagnostic with default zeros has no post-B lifecycle
        # witness: it cannot masquerade as measured or provider-reported zero.
        original = deepcopy(fixtures["F_READY_ONE"])
        c = deepcopy(posts(original)[0]["payload_snapshot"]["execution_receipt"])
        c.update(elapsed_ms=0, input_tokens=0, output_tokens=0)
        doc = dict(root=root, valuation_task=selector(s)["task_id"], receipts=[c])
        text = json.dumps(doc)
        loose = dict(
            source_namespace=dict(kind="RETAINED_LOCAL_FIXTURE", anchor_digest=sha(text)),
            retained_json=text,
            records=[],
        )
        e = project(loose)
        expect(e, "NOT_READY")
        assert len(e["dispatches"]) == 1
        assert e["dispatches"][0]["model_turn_elapsed"]["value"] is None
        assert e["dispatches"][0]["model_turn_elapsed"]["missing_reason"] == "UNPROVEN_DEFAULT"
        assert_blocker("B03_unproven_receipt_zero", fixtures)
        assert_blocker("B03_wrong_receipt_schema", fixtures)
    elif scenario == "T34":
        s["trusted"] = True
        s["legacy"] = True
        root, r = current(s)
        r["run_id"] = "RUN-WRONG"
        seal(s)
        expect(project(s), "NOT_READY", "IDENTITY_MISMATCH")
    elif scenario == "T35":
        obj(s, "Review")["run_id"] = "RUN-WRONG"
        obj(s, "Review")["input_snapshot_hash"] = None
        seal(s)
        expect(project(s), "NOT_READY", "IDENTITY_MISMATCH")
    elif scenario == "T36":
        root, r = current(s)
        root["execution_mode"] = "RECOVERABLE_V1"
        seal(s)
        expect(project(s), "NOT_READY", "UNSUPPORTED_PROFILE")
        for name in (
            "B03_fundamental_profile",
            "B03_non_opt_in",
            "B03_route_mismatch",
            "B03_multiroute",
            "B03_forbidden_fallback",
            "B03_forbidden_retry",
        ):
            assert_blocker(name, fixtures)


def posts_from_root(root):
    return [b for b in root["resolved_inputs"].values() if b["step_id"].endswith(":receipt")]


def independent_digest(value, tag):
    canonical = json.dumps(
        {"schema": tag, "value": value},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def released_context(s):
    from src.domain.released_research_result import ReleasedResearchResult

    native = ReleasedResearchResult(
        result_id="RELEASE-LOCAL",
        run_id=selector(s)["run_id"],
        canonical_record_id="CER-LOCAL",
        released_at="2026-09-14T00:00:00Z",
    )
    obj(s, "Application")["status"] = "RELEASED"
    s["records"].append(
        record("Release", native.run_id, canonical_value(native), "SYNTHETIC_CONTEXT")
    )
    seal(s)


def change_post(s, index, mutate):
    root, r = current(s)
    b = posts(s)[index]
    old = b["resolved_input_binding_id"]
    mutate(b["payload_snapshot"])
    b["input_digest"] = digest(b["payload_snapshot"], "wp02-input-payload/v1")
    b["resolved_input_binding_id"] = digest(
        {k: v for k, v in b.items() if k != "resolved_input_binding_id"}, b["schema_version"]
    )
    root["resolved_inputs"].pop(old)
    root["resolved_inputs"][b["resolved_input_binding_id"]] = b
    r["resolved_input_binding_ids"] = [
        b["resolved_input_binding_id"] if x == old else x for x in r["resolved_input_binding_ids"]
    ]
    r["observed_execution"]["wp03_context"]["receipt_refs"][index] = b["resolved_input_binding_id"]
    r["observed_execution"]["wp03_context"]["calls"][index] = deepcopy(
        b["payload_snapshot"]["execution_receipt"]
    )
    resign_result(s)


def mutate_blocker(name, fixtures):
    fixture = (
        "method"
        if name.startswith("B05_") or name == "B02_nested_method_shape_violation"
        else "F_READY_ONE"
    )
    if name == "B03_two_calls_without_retrieval":
        fixture = "F_READY_TWO"
    s = deepcopy(fixtures[fixture])
    malicious = {
        "schema_version": "https://sentinel.invalid/private?token=REMEDIATION_SECRET",
        "full_prompt": "REMEDIATION_PROMPT",
    }
    if name.startswith("B01_"):
        if name == "B01_plain_missing_review_control":
            s["records"] = [r for r in s["records"] if r["owner"] != "Review"]
        else:
            review = obj(s, "Review")
            review["run_id"] = "RUN-FOREIGN"
            review["input_snapshot_hash" if name.endswith("missing_hash") else "reviewer"] = None
    elif name == "B02_nested_reviewer_payload_leak":
        obj(s, "Review")["reviewer"] = malicious
    elif name == "B02_nested_subject_refs_leak":
        obj(s, "Review")["checks"][0]["subject_refs"] = malicious
    elif name == "B02_nested_release_shape_violation":
        released_context(s)
        obj(s, "Release")["canonical_record_id"] = malicious
    elif name == "B02_nested_method_shape_violation":
        o = obj(s, "Method")["entry"]["observations"][-1]
        o["diagnostic_code"] = malicious
        o["observation_id"] = independent_digest(
            {k: v for k, v in o.items() if k != "observation_id"}, o["schema_version"]
        )
    elif name == "B02_nested_dispatch_shape_violation":
        change_receipt(s, 0, response_request_id=malicious)
    elif name == "B02_nested_source_ref_shape_violation":
        obj(s, "Review")["source_refs"] = [malicious]
    elif name.startswith("B04_"):
        if name != "B04_valid_control":
            field = name.removeprefix("B04_application_").removesuffix("_conflict")
            obj(s, "Application")[field] = "FOREIGN"
    elif name.startswith("B05_"):
        if name != "B05_valid_method_plus_legacy_companion_control":
            package = obj(s, "Method")
            o = package["entry"]["observations"][-1]
            fields = {
                "B05_cross_run_method_observation": "run_id",
                "B05_cross_task_method_observation": "task_id",
                "B05_wrong_requirement_observation": "requirement_id",
                "B05_wrong_B_method_observation": "B_ref",
                "B05_wrong_A_method_observation": "admission_binding_id",
                "B05_wrong_owner_observation": "owner_id",
                "B05_wrong_source_manifest_observation": "source_manifest_digest",
                "B05_wrong_input_identity_observation": "input_identity_digest",
                "B05_wrong_selected_source": "calculation_ref",
            }
            o[fields[name]] = "FOREIGN"
            o["observation_id"] = independent_digest(
                {k: v for k, v in o.items() if k != "observation_id"}, o["schema_version"]
            )
    elif name.startswith("B03_"):
        changes = {
            "B03_wrong_receipt_schema": dict(schema_version="legacy-call/v0"),
            "B03_unproven_receipt_zero": dict(
                usage_coverage="UNKNOWN", input_tokens=0, output_tokens=0
            ),
            "B03_wrong_outcome_digest": dict(outcome_digest="sha256:" + "0" * 64),
            "B03_successful_R_unknown_call": dict(phase="RESULT_UNKNOWN"),
            "B03_forbidden_fallback": dict(fallback_used=True),
            "B03_forbidden_retry": dict(retry_used=True),
            "B03_turn_conflict": dict(turn_number=2),
            "B03_pre_B_conflict": dict(pre_call_B_ref="FOREIGN"),
            "B03_route_mismatch": dict(resolved_route="mimo-direct"),
        }
        if name in changes:
            change_receipt(s, 0, **changes[name])
        elif name == "B03_post_counter_conflict":
            change_post(
                s,
                0,
                lambda p: p["interaction_counters"].update(
                    interaction_id="INTERACTION-FOREIGN", calls=[]
                ),
            )
        elif name == "B03_post_receipt_ref_conflict":
            change_post(s, 0, lambda p: p["interaction_counters"].update(receipt_refs=["FOREIGN"]))
        elif name == "B03_post_count_conflict":
            change_post(
                s, 0, lambda p: p["interaction_counters"].update(client_physical_dispatch_count=2)
            )
        elif name == "B03_two_calls_without_retrieval":
            change_post(
                s, 0, lambda p: p.update(response={"kind": "FINAL", "answer": {}, "request": None})
            )
        elif name == "B03_non_opt_in":
            current(s)[1]["observed_execution"].pop("wp03_context")
            resign_result(s)
        elif name == "B03_fundamental_profile":
            a = obj(s, "Repository")["attempts"][selector(s)["task_id"]]["admission"]
            a["authorized_input_requirements"]["task"]["assigned_agent"] = "fundamental_analyst"
        elif name == "B03_multiroute":
            config = deepcopy(
                posts(s)[0]["payload_snapshot"]["execution_receipt"]["configuration_snapshot"]
            )
            config["route"] = ["teamorouter-sol", "mimo-direct"]
            change_receipt(s, 0, configuration_snapshot=config)
        else:
            raise AssertionError(name)
    else:
        raise AssertionError(name)
    seal(s)
    return s


def assert_blocker(name, fixtures):
    s = mutate_blocker(name, fixtures)
    original = deepcopy(s)
    e = project(s)
    assert s == original
    if name == "B01_plain_missing_review_control":
        expect(e, "PARTIALLY_READY", "MISSING_REVIEW")
    elif name == "B04_valid_control":
        expect(e, "READY")
    elif name == "B05_valid_method_plus_legacy_companion_control":
        expect(e, "PARTIALLY_READY", "METHOD_IDENTITY_UNKNOWN")
        assert e["method_dependency_context"][0]["capability_id"] == "revenue_growth"
    elif name == "B03_unproven_receipt_zero":
        assert e["readiness_state"] in ("PARTIALLY_READY", "NOT_READY")
        for k in ("input_tokens", "output_tokens"):
            assert e["dispatches"][0][k]["value"] is None
            assert e["dispatches"][0][k]["provenance"] == "UNKNOWN"
            assert metric(e, k)["complete_total"]["value"] is None
    else:
        expect(e, "NOT_READY")
        if name.startswith(("B01_", "B02_", "B04_", "B05_")) or name == "B03_wrong_outcome_digest":
            assert "IDENTITY_MISMATCH" in e["readiness_reasons"]
        assert all(
            metric(e, k)["complete_total"]["value"] is None
            for k in ("input_tokens", "output_tokens")
        )
    assert "REMEDIATION_SECRET" not in json.dumps(e) and "REMEDIATION_PROMPT" not in json.dumps(e)
    return e


@pytest.mark.parametrize("case", SPEC["remediation_cases"])
def test_blocker(case, fixtures):
    assert_blocker(case, fixtures)


def test_blocker_native_response_schema_control():
    from src.agentic.valuation_context import StandardResearchAgentStructuredOutput, ValuationTurn
    from src.application.evaluation_input import RESPONSE_SCHEMAS

    assert RESPONSE_SCHEMAS == {
        i: digest(model.model_json_schema(), "model-response-schema/v1")
        for i, model in ((1, ValuationTurn), (2, StandardResearchAgentStructuredOutput))
    }


def test_blocker_safe_dotted_selector_control(fixtures):
    e = project(fixtures["F_READY_ONE"])
    expect(e, "READY")
    assert any(
        "/payload_snapshot/execution_receipt/input_tokens" in r["field_selectors"]
        for r in e["dispatches"][0]["input_tokens"]["source_refs"]
    )
    from src.application.evaluation_input import _native_selectors

    _native_selectors(["structured_output.summary"])
    _native_selectors(["/structured_output/summary"])
    for value in (
        {"full_prompt": "REMEDIATION_PROMPT"},
        [{"schema_version": "https://sentinel.invalid"}],
        ["https://sentinel.invalid"],
        ["/private/file"],
    ):
        with pytest.raises(ValueError):
            _native_selectors(value)
