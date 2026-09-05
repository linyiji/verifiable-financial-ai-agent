"""Durable exact-byte retention for governed generated capabilities."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from src.capabilities.generated.models import GeneratedCapabilityCandidate
from src.domain.base import JsonObject
from src.domain.capability import GeneratedCapabilityArtifactRecord, GeneratedCapabilityRecord
from src.tooling.generated_sandbox import SandboxRequest

_ARTIFACT_PREFIX = "generated-artifact://sha256/"


class GeneratedArtifactRetentionError(ValueError):
    """The exact generated build input could not be retained or verified."""


@dataclass(frozen=True, slots=True)
class ReconstructedGeneratedBuildInput:
    source_bytes: bytes
    test_bytes: bytes
    runtime_image_identity: str
    spec_bytes: bytes | None = None
    spec_sha256: str | None = None
    compiler_id: str | None = None
    compiler_version: str | None = None
    compiler_runtime_policy: str | None = None

    @property
    def source_code(self) -> str:
        return self.source_bytes.decode("utf-8", errors="strict")

    @property
    def unit_tests(self) -> str:
        return self.test_bytes.decode("utf-8", errors="strict")

    def sandbox_request(
        self,
        fixture: JsonObject,
        *,
        entrypoint: str = "execute",
    ) -> SandboxRequest:
        return SandboxRequest(
            source=self.source_code,
            test_source=self.unit_tests,
            fixture=fixture,
            entrypoint=entrypoint,
        )


class GeneratedCapabilityArtifactStore:
    """Content-addressed immutable blobs plus verified internal-audit retrieval.

    Source and test text is encoded exactly once as UTF-8. Existing blob paths
    are never overwritten: identical content is reused and differing content at
    the same address is treated as corruption.
    """

    def __init__(
        self,
        artifact_root: str | Path,
        *,
        forbidden_values: Iterable[str | bytes] = (),
    ) -> None:
        requested = Path(artifact_root).expanduser()
        if requested == Path(requested.anchor):
            raise GeneratedArtifactRetentionError(
                "filesystem root cannot be used as generated artifact root"
            )
        if requested.is_symlink():
            raise GeneratedArtifactRetentionError("generated artifact root must not be a symlink")
        requested.mkdir(parents=True, exist_ok=True)
        self.root = requested.resolve(strict=True)
        if not self.root.is_dir():
            raise GeneratedArtifactRetentionError("generated artifact root must be a directory")
        self._blob_root = self.root / "blobs" / "sha256"
        self._blob_root.mkdir(parents=True, exist_ok=True)
        self._manifest_root = self.root / "manifests" / "sha256"
        self._manifest_root.mkdir(parents=True, exist_ok=True)
        self._forbidden_values = tuple(
            value.encode("utf-8") if isinstance(value, str) else bytes(value)
            for value in forbidden_values
            if value
        )

    def retain(
        self,
        *,
        run_id: str,
        generated: GeneratedCapabilityRecord,
        candidate: GeneratedCapabilityCandidate,
        runtime_image_identity: str,
    ) -> GeneratedCapabilityArtifactRecord:
        if (
            not runtime_image_identity.strip()
            or runtime_image_identity == "UNRECORDED_LEGACY_RUNTIME"
        ):
            raise GeneratedArtifactRetentionError(
                "accepted generated build requires an explicit runtime image identity"
            )
        if generated.run_id != run_id:
            raise GeneratedArtifactRetentionError("generated capability belongs to another run")
        if (
            generated.capability_id != candidate.output.capability_id
            or generated.capability_version != candidate.output.version
        ):
            raise GeneratedArtifactRetentionError(
                "generated capability identity differs from retained build input"
            )

        source_bytes = exact_generated_bytes(candidate.output.source_code)
        test_bytes = exact_generated_bytes(candidate.output.unit_tests)
        retained_inputs = [source_bytes, test_bytes]
        if candidate.spec_bytes is not None:
            retained_inputs.append(candidate.spec_bytes)
        self._reject_sensitive_content(*retained_inputs)
        self._validate_spec_preimage(candidate)
        source_sha256 = content_sha256(source_bytes)
        test_sha256 = content_sha256(test_bytes)
        if candidate.implementation_hash != source_sha256:
            raise GeneratedArtifactRetentionError(
                "implementation hash does not bind the exact generated source bytes"
            )
        if generated.implementation_hash != source_sha256:
            raise GeneratedArtifactRetentionError(
                "generated record does not bind the exact generated source bytes"
            )

        source_ref = self._put(source_sha256, source_bytes)
        test_ref = self._put(test_sha256, test_bytes)
        record = GeneratedCapabilityArtifactRecord(
            run_id=run_id,
            build_id=candidate.build_id,
            generated_capability_id=generated.generated_capability_id,
            capability_id=generated.capability_id,
            capability_version=generated.capability_version,
            source_artifact_id=source_sha256,
            source_artifact_ref=source_ref,
            source_sha256=source_sha256,
            source_size_bytes=len(source_bytes),
            test_artifact_id=test_sha256,
            test_artifact_ref=test_ref,
            test_sha256=test_sha256,
            test_size_bytes=len(test_bytes),
            implementation_hash=candidate.implementation_hash,
            runtime_image_identity=runtime_image_identity,
        )
        self._retain_spec_manifest(record, candidate)
        return record

    def reconstruct(
        self,
        record: GeneratedCapabilityArtifactRecord,
    ) -> ReconstructedGeneratedBuildInput:
        source = self._read_verified(
            artifact_ref=record.source_artifact_ref,
            artifact_id=record.source_artifact_id,
            expected_hash=record.source_sha256,
            expected_size=record.source_size_bytes,
        )
        tests = self._read_verified(
            artifact_ref=record.test_artifact_ref,
            artifact_id=record.test_artifact_id,
            expected_hash=record.test_sha256,
            expected_size=record.test_size_bytes,
        )
        if content_sha256(source) != record.implementation_hash:
            raise GeneratedArtifactRetentionError(
                "retained source no longer matches implementation hash"
            )
        manifest = self._read_spec_manifest(record)
        spec_bytes: bytes | None = None
        if manifest is not None:
            spec_bytes = self._read_verified(
                artifact_ref=str(manifest["spec_artifact_ref"]),
                artifact_id=str(manifest["spec_sha256"]),
                expected_hash=str(manifest["spec_sha256"]),
                expected_size=int(manifest["spec_size_bytes"]),
            )
        return ReconstructedGeneratedBuildInput(
            source_bytes=source,
            test_bytes=tests,
            runtime_image_identity=record.runtime_image_identity,
            spec_bytes=spec_bytes,
            spec_sha256=str(manifest["spec_sha256"]) if manifest else None,
            compiler_id=str(manifest["compiler_id"]) if manifest else None,
            compiler_version=str(manifest["compiler_version"]) if manifest else None,
            compiler_runtime_policy=(
                str(manifest["compiler_runtime_policy"]) if manifest else None
            ),
        )

    def reconstruct_from_spec(
        self,
        record: GeneratedCapabilityArtifactRecord,
        request: object,
    ) -> ReconstructedGeneratedBuildInput:
        """Independently recompile a retained canonical Spec and verify exact bytes."""

        from src.capabilities.generated.contract import GeneratedCapabilityRequestV1
        from src.capabilities.generated.spec import (
            GENERATED_CAPABILITY_COMPILER_ID,
            GENERATED_CAPABILITY_COMPILER_VERSION,
            GENERATED_CAPABILITY_RUNTIME_POLICY,
            GeneratedCapabilityCompilerV1,
            canonical_spec_bytes,
            decode_generated_capability_spec,
        )

        if not isinstance(request, GeneratedCapabilityRequestV1):
            raise GeneratedArtifactRetentionError("owned request is required for reconstruction")
        reconstructed = self.reconstruct(record)
        if reconstructed.spec_bytes is None:
            raise GeneratedArtifactRetentionError("retained generated build has no Spec preimage")
        if (
            reconstructed.compiler_id != GENERATED_CAPABILITY_COMPILER_ID
            or reconstructed.compiler_version != GENERATED_CAPABILITY_COMPILER_VERSION
            or reconstructed.compiler_runtime_policy != GENERATED_CAPABILITY_RUNTIME_POLICY
        ):
            raise GeneratedArtifactRetentionError("retained compiler identity is unsupported")
        try:
            raw = json.loads(reconstructed.spec_bytes.decode("utf-8", errors="strict"))
            spec = decode_generated_capability_spec(raw)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise GeneratedArtifactRetentionError(
                "retained Spec is not canonical and valid"
            ) from exc
        if canonical_spec_bytes(spec) != reconstructed.spec_bytes:
            raise GeneratedArtifactRetentionError("retained Spec bytes are not canonical")
        compiled = GeneratedCapabilityCompilerV1().compile(request, spec)
        if (
            exact_generated_bytes(compiled.output.source_code) != reconstructed.source_bytes
            or exact_generated_bytes(compiled.output.unit_tests) != reconstructed.test_bytes
            or compiled.spec_sha256 != reconstructed.spec_sha256
        ):
            raise GeneratedArtifactRetentionError(
                "retained Spec/compiler reconstruction differs from accepted bytes"
            )
        return reconstructed

    def _retain_spec_manifest(
        self,
        record: GeneratedCapabilityArtifactRecord,
        candidate: GeneratedCapabilityCandidate,
    ) -> None:
        values = (
            candidate.spec_bytes,
            candidate.spec_sha256,
            candidate.compiler_id,
            candidate.compiler_version,
            candidate.compiler_runtime_policy,
        )
        if all(value is None for value in values):
            return
        assert candidate.spec_bytes is not None
        assert candidate.spec_sha256 is not None
        spec_ref = self._put(candidate.spec_sha256, candidate.spec_bytes)
        manifest = {
            "schema_version": "generated-capability-reconstruction/v1",
            "run_id": record.run_id,
            "build_id": record.build_id,
            "implementation_hash": record.implementation_hash,
            "source_sha256": record.source_sha256,
            "test_sha256": record.test_sha256,
            "runtime_image_identity": record.runtime_image_identity,
            "spec_artifact_ref": spec_ref,
            "spec_sha256": candidate.spec_sha256,
            "spec_size_bytes": len(candidate.spec_bytes),
            "compiler_id": candidate.compiler_id,
            "compiler_version": candidate.compiler_version,
            "compiler_runtime_policy": candidate.compiler_runtime_policy,
        }
        manifest_bytes = json.dumps(
            manifest,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        self._put_immutable_path(
            self._manifest_path(record.run_id, record.build_id), manifest_bytes
        )

    @staticmethod
    def _validate_spec_preimage(candidate: GeneratedCapabilityCandidate) -> None:
        values = (
            candidate.spec_bytes,
            candidate.spec_sha256,
            candidate.compiler_id,
            candidate.compiler_version,
            candidate.compiler_runtime_policy,
        )
        if all(value is None for value in values):
            return
        if any(value is None for value in values):
            raise GeneratedArtifactRetentionError("generated Spec/compiler identity is incomplete")
        assert candidate.spec_bytes is not None
        assert candidate.spec_sha256 is not None
        if content_sha256(candidate.spec_bytes) != candidate.spec_sha256:
            raise GeneratedArtifactRetentionError("generated Spec hash does not match exact bytes")
        try:
            decoded = json.loads(candidate.spec_bytes.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GeneratedArtifactRetentionError(
                "generated Spec bytes are not canonical JSON"
            ) from exc
        canonical = json.dumps(
            decoded,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if not isinstance(decoded, dict) or canonical != candidate.spec_bytes:
            raise GeneratedArtifactRetentionError("generated Spec bytes are not canonical JSON")

    def _read_spec_manifest(
        self,
        record: GeneratedCapabilityArtifactRecord,
    ) -> JsonObject | None:
        target = self._manifest_path(record.run_id, record.build_id)
        if not target.exists():
            return None
        raw = self._read_path(target)
        try:
            manifest = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GeneratedArtifactRetentionError(
                "generated reconstruction manifest is invalid"
            ) from exc
        if not isinstance(manifest, dict):
            raise GeneratedArtifactRetentionError("generated reconstruction manifest is invalid")
        expected = {
            "run_id": record.run_id,
            "build_id": record.build_id,
            "implementation_hash": record.implementation_hash,
            "source_sha256": record.source_sha256,
            "test_sha256": record.test_sha256,
            "runtime_image_identity": record.runtime_image_identity,
        }
        if manifest.get("schema_version") != "generated-capability-reconstruction/v1" or any(
            manifest.get(key) != value for key, value in expected.items()
        ):
            raise GeneratedArtifactRetentionError(
                "generated reconstruction manifest identity mismatch"
            )
        required = {
            "spec_artifact_ref",
            "spec_sha256",
            "spec_size_bytes",
            "compiler_id",
            "compiler_version",
            "compiler_runtime_policy",
        }
        if not required.issubset(manifest):
            raise GeneratedArtifactRetentionError("generated reconstruction manifest is incomplete")
        return manifest

    def _manifest_path(self, run_id: str, build_id: str) -> Path:
        digest = hashlib.sha256(f"{run_id}\0{build_id}".encode()).hexdigest()
        target = self._manifest_root / digest
        self._assert_safe_blob_path(target)
        return target

    def _put_immutable_path(self, target: Path, content: bytes) -> None:
        if target.exists():
            if self._read_path(target) != content:
                raise GeneratedArtifactRetentionError(
                    "immutable generated reconstruction manifest differs"
                )
            return
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o400)
            try:
                os.link(temporary, target)
                _fsync_directory(target.parent)
            except FileExistsError:
                if self._read_path(target) != content:
                    raise GeneratedArtifactRetentionError(
                        "immutable generated reconstruction manifest differs"
                    ) from None
        finally:
            if temporary.exists():
                temporary.unlink()

    def _put(self, content_hash: str, content: bytes) -> str:
        if not content:
            raise GeneratedArtifactRetentionError("generated artifact must not be empty")
        digest = _digest(content_hash)
        target = self._blob_root / digest
        self._assert_safe_blob_path(target)
        if target.exists():
            if self._read_path(target) != content:
                raise GeneratedArtifactRetentionError(
                    "content-addressed generated artifact hash collision or corruption"
                )
            return f"{_ARTIFACT_PREFIX}{digest}"

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{digest}.", suffix=".tmp", dir=self._blob_root
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o400)
            try:
                os.link(temporary, target)
                _fsync_directory(self._blob_root)
            except FileExistsError:
                if self._read_path(target) != content:
                    raise GeneratedArtifactRetentionError(
                        "content-addressed generated artifact hash collision or corruption"
                    ) from None
        finally:
            if temporary.exists():
                temporary.unlink()
        return f"{_ARTIFACT_PREFIX}{digest}"

    def _read_verified(
        self,
        *,
        artifact_ref: str,
        artifact_id: str,
        expected_hash: str,
        expected_size: int,
    ) -> bytes:
        if artifact_id != expected_hash:
            raise GeneratedArtifactRetentionError("artifact id does not equal its content hash")
        digest = _digest(expected_hash)
        if artifact_ref != f"{_ARTIFACT_PREFIX}{digest}":
            raise GeneratedArtifactRetentionError("artifact reference does not match content hash")
        target = self._blob_root / digest
        self._assert_safe_blob_path(target)
        content = self._read_path(target)
        if len(content) != expected_size:
            raise GeneratedArtifactRetentionError("generated artifact byte size mismatch")
        if content_sha256(content) != expected_hash:
            raise GeneratedArtifactRetentionError("generated artifact content hash mismatch")
        return content

    def _read_path(self, target: Path) -> bytes:
        if target.is_symlink() or not target.is_file():
            raise GeneratedArtifactRetentionError("generated artifact blob is missing or unsafe")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(target, flags)
        except OSError as exc:
            raise GeneratedArtifactRetentionError(
                "generated artifact blob could not be opened safely"
            ) from exc
        with os.fdopen(descriptor, "rb") as stream:
            return stream.read()

    def _assert_safe_blob_path(self, target: Path) -> None:
        relative = PurePosixPath(target.relative_to(self.root).as_posix())
        if relative.is_absolute() or ".." in relative.parts:
            raise GeneratedArtifactRetentionError("generated artifact path escapes controlled root")
        current = self.root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise GeneratedArtifactRetentionError(
                    "symlinks are forbidden inside generated artifact root"
                )

    def _reject_sensitive_content(self, *contents: bytes) -> None:
        if any(value in content for value in self._forbidden_values for content in contents):
            raise GeneratedArtifactRetentionError(
                "generated Spec, source, or tests contain configured credential bytes"
            )


def exact_generated_bytes(source: str) -> bytes:
    return source.encode("utf-8", errors="strict")


def content_sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def generated_text_sha256(source: str) -> str:
    return content_sha256(exact_generated_bytes(source))


def _digest(content_hash: str) -> str:
    if len(content_hash) != 71 or not content_hash.startswith("sha256:"):
        raise GeneratedArtifactRetentionError("invalid generated artifact sha256 identity")
    digest = content_hash.removeprefix("sha256:")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise GeneratedArtifactRetentionError("invalid generated artifact sha256 identity") from exc
    return digest


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
