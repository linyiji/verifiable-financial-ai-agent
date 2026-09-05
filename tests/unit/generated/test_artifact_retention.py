from __future__ import annotations

import hashlib
import os

import pytest

from src.capabilities.generated.artifacts import (
    GeneratedArtifactRetentionError,
    GeneratedCapabilityArtifactStore,
    generated_text_sha256,
)
from src.capabilities.generated.contract import GeneratedCapabilityRequestV1
from src.capabilities.generated.models import CodeBuilderOutput, GeneratedCapabilityCandidate
from src.capabilities.generated.spec import GeneratedCapabilityCompilerV1, expected_spec
from src.domain.capability import GeneratedCapabilityRecord
from tests.unit.generated.test_contract import build_request

SOURCE = "# exact UTF-8: π\r\ndef execute(inputs):\r\n    return {'value': inputs['value']}"
TESTS = "# exact test: 雪\ndef run_tests(execute, fixture):\n    assert execute(fixture)"
RUNTIME_IMAGE = (
    "python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534"
)


def _candidate() -> GeneratedCapabilityCandidate:
    output = CodeBuilderOutput(
        capability_id="exact_bytes",
        version="1.0.0-generated",
        purpose="Prove exact generated artifact retention.",
        input_schema={"value": "decimal"},
        output_schema={"value": "decimal"},
        formula_id="exact_bytes_v1",
        formula_description="identity",
        source_code=SOURCE,
        unit_tests=TESTS,
        financial_invariants=[],
        allowed_imports=[],
    )
    return GeneratedCapabilityCandidate(
        build_id="BUILD-EXACT",
        output=output,
        implementation_hash=generated_text_sha256(SOURCE),
        provider="teamorouter",
        requested_model="gpt-5.6-sol",
        actual_model="gpt-5.6-sol",
        attempted_models=("gpt-5.6-sol",),
        input_tokens=1,
        output_tokens=1,
        latency_ms=1.0,
    )


def _generated(candidate: GeneratedCapabilityCandidate) -> GeneratedCapabilityRecord:
    return GeneratedCapabilityRecord(
        generated_capability_id="GEN-EXACT",
        run_id="RUN-EXACT",
        task_id="TASK-EXACT",
        gap_id="GAP-EXACT",
        capability_id=candidate.output.capability_id,
        capability_version=candidate.output.version,
        formula_id=candidate.output.formula_id,
        purpose=candidate.output.purpose,
        input_schema=candidate.output.input_schema,
        output_schema=candidate.output.output_schema,
        formula_description=candidate.output.formula_description,
        implementation_hash=candidate.implementation_hash,
        source_ref="generated://BUILD-EXACT/source.py",
        unit_test_ref="generated://BUILD-EXACT/tests.py",
        runtime_version=f"Python 3.11 ({RUNTIME_IMAGE})",
    )


def _retain(tmp_path):
    candidate = _candidate()
    generated = _generated(candidate)
    store = GeneratedCapabilityArtifactStore(tmp_path / "generated")
    record = store.retain(
        run_id=generated.run_id,
        generated=generated,
        candidate=candidate,
        runtime_image_identity=RUNTIME_IMAGE,
    )
    return store, record, candidate, generated


def _blob_path(store: GeneratedCapabilityArtifactStore, content_hash: str):
    return store.root / "blobs" / "sha256" / content_hash.removeprefix("sha256:")


def test_exact_unnormalized_utf8_bytes_are_content_addressed_and_reconstructable(
    tmp_path,
) -> None:
    store, record, candidate, generated = _retain(tmp_path)

    reconstructed = store.reconstruct(record)
    request = reconstructed.sandbox_request({"value": "1"})
    assert reconstructed.source_bytes == SOURCE.encode("utf-8")
    assert reconstructed.test_bytes == TESTS.encode("utf-8")
    assert request.source == candidate.output.source_code
    assert request.test_source == candidate.output.unit_tests
    assert reconstructed.runtime_image_identity == RUNTIME_IMAGE
    assert record.build_id == candidate.build_id
    assert record.generated_capability_id == generated.generated_capability_id
    assert record.source_sha256 == candidate.implementation_hash
    assert record.source_size_bytes == len(SOURCE.encode("utf-8"))
    assert record.test_size_bytes == len(TESTS.encode("utf-8"))

    legacy_normalized = SOURCE.replace("\r\n", "\n").rstrip() + "\n"
    legacy_hash = "sha256:" + hashlib.sha256(legacy_normalized.encode("utf-8")).hexdigest()
    assert record.source_sha256 != legacy_hash

    repeated = store.retain(
        run_id=generated.run_id,
        generated=generated,
        candidate=candidate,
        runtime_image_identity=RUNTIME_IMAGE,
    )
    assert repeated.source_artifact_ref == record.source_artifact_ref
    assert repeated.test_artifact_ref == record.test_artifact_ref
    assert len(list((store.root / "blobs" / "sha256").iterdir())) == 2


@pytest.mark.parametrize("artifact", ["source", "test"])
def test_retrieval_rejects_source_and_test_blob_tamper(tmp_path, artifact: str) -> None:
    store, record, _, _ = _retain(tmp_path)
    content_hash = record.source_sha256 if artifact == "source" else record.test_sha256
    path = _blob_path(store, content_hash)
    os.chmod(path, 0o600)
    path.write_bytes(b"tampered")

    with pytest.raises(GeneratedArtifactRetentionError, match="size mismatch|hash mismatch"):
        store.reconstruct(record)


@pytest.mark.parametrize(
    "updates, expected",
    [
        ({"source_size_bytes": 1}, "size mismatch"),
        ({"test_size_bytes": 1}, "size mismatch"),
        ({"source_artifact_ref": "generated-artifact://sha256/" + "0" * 64}, "reference"),
        ({"implementation_hash": "sha256:" + "0" * 64}, "implementation hash"),
    ],
)
def test_retrieval_rejects_binding_metadata_tamper(tmp_path, updates, expected) -> None:
    store, record, _, _ = _retain(tmp_path)
    tampered = record.model_copy(update=updates)

    with pytest.raises(GeneratedArtifactRetentionError, match=expected):
        store.reconstruct(tampered)


def test_existing_content_address_is_never_overwritten(tmp_path) -> None:
    store, record, candidate, generated = _retain(tmp_path)
    source_path = _blob_path(store, record.source_sha256)
    os.chmod(source_path, 0o600)
    source_path.write_bytes(b"corrupt-existing-content")

    with pytest.raises(GeneratedArtifactRetentionError, match="collision or corruption"):
        store.retain(
            run_id=generated.run_id,
            generated=generated,
            candidate=candidate,
            runtime_image_identity=RUNTIME_IMAGE,
        )
    assert source_path.read_bytes() == b"corrupt-existing-content"


def test_configured_credentials_are_rejected_before_any_blob_is_written(tmp_path) -> None:
    secret = b"provider-token-that-must-not-persist"
    candidate = _candidate()
    source = f"TOKEN = {secret.decode()!r}\n" + candidate.output.source_code
    output = candidate.output.model_copy(update={"source_code": source})
    candidate = GeneratedCapabilityCandidate(
        build_id=candidate.build_id,
        output=output,
        implementation_hash=generated_text_sha256(source),
        provider=candidate.provider,
        requested_model=candidate.requested_model,
        actual_model=candidate.actual_model,
        attempted_models=candidate.attempted_models,
        input_tokens=candidate.input_tokens,
        output_tokens=candidate.output_tokens,
        latency_ms=candidate.latency_ms,
    )
    generated = _generated(candidate)
    store = GeneratedCapabilityArtifactStore(
        tmp_path / "generated",
        forbidden_values=(secret,),
    )

    with pytest.raises(GeneratedArtifactRetentionError, match="credential bytes"):
        store.retain(
            run_id=generated.run_id,
            generated=generated,
            candidate=candidate,
            runtime_image_identity=RUNTIME_IMAGE,
        )
    assert list((store.root / "blobs" / "sha256").iterdir()) == []


def test_spec_compiler_preimage_reconstructs_exact_accepted_source_and_tests(tmp_path) -> None:
    request = GeneratedCapabilityRequestV1.from_build_request(build_request())
    compiled = GeneratedCapabilityCompilerV1().compile(request, expected_spec(request))
    candidate = GeneratedCapabilityCandidate(
        build_id=build_request().build_id,
        output=compiled.output,
        implementation_hash=generated_text_sha256(compiled.output.source_code),
        provider="mimo",
        requested_model="mimo-v2.5",
        actual_model="mimo-v2.5",
        attempted_models=("mimo-v2.5",),
        input_tokens=1,
        output_tokens=1,
        latency_ms=1.0,
        spec_bytes=compiled.spec_bytes,
        spec_sha256=compiled.spec_sha256,
        compiler_id=compiled.compiler_id,
        compiler_version=compiled.compiler_version,
        compiler_runtime_policy=compiled.runtime_policy,
    )
    generated = _generated(candidate).model_copy(
        update={"run_id": "RUN-EXACT", "task_id": "TASK-EXACT"}
    )
    store = GeneratedCapabilityArtifactStore(tmp_path / "generated")

    record = store.retain(
        run_id="RUN-EXACT",
        generated=generated,
        candidate=candidate,
        runtime_image_identity=RUNTIME_IMAGE,
    )
    reconstructed = store.reconstruct_from_spec(record, request)

    assert reconstructed.spec_bytes == compiled.spec_bytes
    assert reconstructed.spec_sha256 == compiled.spec_sha256
    assert reconstructed.compiler_id == compiled.compiler_id
    assert reconstructed.compiler_version == compiled.compiler_version
    assert reconstructed.compiler_runtime_policy == compiled.runtime_policy
    assert reconstructed.source_bytes == compiled.output.source_code.encode("utf-8")
    assert reconstructed.test_bytes == compiled.output.unit_tests.encode("utf-8")
    assert len(list((store.root / "blobs" / "sha256").iterdir())) == 3


def test_configured_credential_is_rejected_from_spec_preimage(tmp_path) -> None:
    secret = b"credential-that-must-not-enter-spec"
    original = _candidate()
    candidate = GeneratedCapabilityCandidate(
        build_id=original.build_id,
        output=original.output,
        implementation_hash=original.implementation_hash,
        provider=original.provider,
        requested_model=original.requested_model,
        actual_model=original.actual_model,
        attempted_models=original.attempted_models,
        input_tokens=original.input_tokens,
        output_tokens=original.output_tokens,
        latency_ms=original.latency_ms,
        spec_bytes=secret,
        spec_sha256="sha256:" + hashlib.sha256(secret).hexdigest(),
        compiler_id="vfas-generated-capability-compiler",
        compiler_version="1",
        compiler_runtime_policy="python3.11-decimal-sandbox-v1",
    )
    generated = _generated(candidate)
    store = GeneratedCapabilityArtifactStore(
        tmp_path / "generated",
        forbidden_values=(secret,),
    )

    with pytest.raises(GeneratedArtifactRetentionError, match="credential bytes"):
        store.retain(
            run_id=generated.run_id,
            generated=generated,
            candidate=candidate,
            runtime_image_identity=RUNTIME_IMAGE,
        )

    assert list((store.root / "blobs" / "sha256").iterdir()) == []
