"""Durable exact-byte retention for governed generated capabilities."""

from __future__ import annotations

import hashlib
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
        self._reject_sensitive_content(source_bytes, test_bytes)
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
        return GeneratedCapabilityArtifactRecord(
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
        return ReconstructedGeneratedBuildInput(
            source_bytes=source,
            test_bytes=tests,
            runtime_image_identity=record.runtime_image_identity,
        )

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

    def _reject_sensitive_content(self, source: bytes, tests: bytes) -> None:
        if any(value in content for value in self._forbidden_values for content in (source, tests)):
            raise GeneratedArtifactRetentionError(
                "generated source or tests contain configured credential bytes"
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
