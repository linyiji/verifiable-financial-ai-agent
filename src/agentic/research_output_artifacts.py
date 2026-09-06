from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from src.adapters.llm import LLMProviderError, LLMStructuredResponse
from src.data.hashing import canonical_json
from src.domain.agent_output import (
    ResearchAgentOutputRecord,
    ResearchAgentStructuredOutput,
)
from src.domain.task import Task

_ARTIFACT_PREFIX = "agent-output://sha256/"


class ResearchAgentOutputArtifactError(ValueError):
    pass


class ResearchAgentOutputArtifactStore:
    """Retain only strict Agent output and safe invocation metadata.

    The immutable artifact deliberately excludes prompts, provider bodies, raw
    evidence bodies, and model reasoning. It is an internal exact-byte record and
    is not a public execution-audit surface.
    """

    def __init__(
        self,
        artifact_root: str | Path,
        *,
        forbidden_values: Iterable[str | bytes] = (),
    ) -> None:
        requested = Path(artifact_root).expanduser()
        if requested == Path(requested.anchor):
            raise ResearchAgentOutputArtifactError(
                "filesystem root cannot be used as research Agent artifact root"
            )
        if requested.is_symlink():
            raise ResearchAgentOutputArtifactError(
                "research Agent artifact root must not be a symlink"
            )
        requested.mkdir(parents=True, exist_ok=True)
        self.root = requested.resolve(strict=True)
        if not self.root.is_dir():
            raise ResearchAgentOutputArtifactError(
                "research Agent artifact root must be a directory"
            )
        self._blob_root = self.root / "blobs" / "sha256"
        self._blob_root.mkdir(parents=True, exist_ok=True)
        self._forbidden_values = tuple(
            value.encode("utf-8") if isinstance(value, str) else bytes(value)
            for value in forbidden_values
            if value
        )

    def retain_success(
        self,
        *,
        task: Task,
        response: LLMStructuredResponse[ResearchAgentStructuredOutput],
        duration_ms: int,
        input_refs: Sequence[str],
    ) -> ResearchAgentOutputRecord:
        created_at = datetime.now(UTC)
        payload = {
            "schema_version": "research-agent-output/v1",
            "run_id": task.run_id,
            "task_id": task.task_id,
            "actor": task.assigned_agent,
            "provider": response.provider,
            "requested_model": response.requested_model,
            "actual_model": response.actual_model,
            "attempted_models": list(response.attempted_models),
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "duration_ms": duration_ms,
            "status": "SUCCESS",
            "input_refs": list(dict.fromkeys(input_refs)),
            "structured_output": response.output.model_dump(mode="json"),
            "failure_code": None,
            "created_at": created_at.isoformat(),
        }
        return self._retain(task=task, payload=payload, created_at=created_at)

    def retain_failure(
        self,
        *,
        task: Task,
        provider_name: str,
        requested_model: str,
        error: LLMProviderError,
        duration_ms: int,
        input_refs: Sequence[str],
    ) -> ResearchAgentOutputRecord:
        created_at = datetime.now(UTC)
        classification = getattr(error, "failure_classification", None)
        failure_code = getattr(classification, "value", None) or str(
            classification or "provider_failure"
        )
        actual_model = getattr(error, "model", None)
        payload = {
            "schema_version": "research-agent-output/v1",
            "run_id": task.run_id,
            "task_id": task.task_id,
            "actor": task.assigned_agent,
            "provider": getattr(error, "provider", None) or provider_name,
            "requested_model": getattr(error, "requested_model", None) or requested_model,
            "actual_model": actual_model if isinstance(actual_model, str) else None,
            "attempted_models": list(getattr(error, "attempted_models", ())),
            "input_tokens": None,
            "output_tokens": None,
            "duration_ms": duration_ms,
            "status": "FAILED",
            "input_refs": list(dict.fromkeys(input_refs)),
            "structured_output": None,
            "failure_code": failure_code,
            "created_at": created_at.isoformat(),
        }
        return self._retain(task=task, payload=payload, created_at=created_at)

    def read_verified(self, record: ResearchAgentOutputRecord) -> bytes:
        prefix = _ARTIFACT_PREFIX
        if not record.artifact_ref.startswith(prefix):
            raise ResearchAgentOutputArtifactError(
                "research Agent artifact reference is unsupported"
            )
        digest = record.artifact_ref.removeprefix(prefix)
        if f"sha256:{digest}" != record.artifact_sha256:
            raise ResearchAgentOutputArtifactError(
                "research Agent artifact reference does not match its hash"
            )
        target = self._blob_root / digest
        self._assert_safe_path(target)
        try:
            content = target.read_bytes()
        except OSError as exc:
            raise ResearchAgentOutputArtifactError(
                "research Agent artifact is unavailable"
            ) from exc
        if (
            len(content) != record.artifact_size_bytes
            or f"sha256:{hashlib.sha256(content).hexdigest()}" != record.artifact_sha256
        ):
            raise ResearchAgentOutputArtifactError(
                "research Agent artifact failed exact-byte verification"
            )
        return content

    def _retain(
        self,
        *,
        task: Task,
        payload: dict[str, object],
        created_at: datetime,
    ) -> ResearchAgentOutputRecord:
        content = canonical_json(payload)
        if not content:
            raise ResearchAgentOutputArtifactError("research Agent artifact must not be empty")
        for forbidden in self._forbidden_values:
            if forbidden in content:
                raise ResearchAgentOutputArtifactError(
                    "research Agent artifact contains configured secret material"
                )
        digest = hashlib.sha256(content).hexdigest()
        artifact_hash = f"sha256:{digest}"
        target = self._blob_root / digest
        self._assert_safe_path(target)
        self._put_immutable(target, content)
        output_id = f"AGOUT-{uuid5(NAMESPACE_URL, f'{task.run_id}:{task.task_id}:{digest}')}"
        structured = payload.get("structured_output")
        return ResearchAgentOutputRecord(
            output_id=output_id,
            run_id=task.run_id,
            task_id=task.task_id,
            actor=task.assigned_agent,
            provider=str(payload["provider"]),
            requested_model=str(payload["requested_model"]),
            actual_model=(
                str(payload["actual_model"])
                if isinstance(payload.get("actual_model"), str)
                else None
            ),
            attempted_models=[str(value) for value in payload["attempted_models"]],
            input_tokens=(
                int(payload["input_tokens"])
                if isinstance(payload.get("input_tokens"), int)
                else None
            ),
            output_tokens=(
                int(payload["output_tokens"])
                if isinstance(payload.get("output_tokens"), int)
                else None
            ),
            duration_ms=int(payload["duration_ms"]),
            status=str(payload["status"]),
            input_refs=[str(value) for value in payload["input_refs"]],
            structured_output=(
                ResearchAgentStructuredOutput.model_validate(structured)
                if isinstance(structured, dict)
                else None
            ),
            failure_code=(
                str(payload["failure_code"])
                if isinstance(payload.get("failure_code"), str)
                else None
            ),
            artifact_id=artifact_hash,
            artifact_ref=f"{_ARTIFACT_PREFIX}{digest}",
            artifact_sha256=artifact_hash,
            artifact_size_bytes=len(content),
            created_at=created_at,
        )

    def _put_immutable(self, target: Path, content: bytes) -> None:
        if target.exists():
            if target.read_bytes() != content:
                raise ResearchAgentOutputArtifactError(
                    "research Agent artifact hash collision or corruption"
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
            except FileExistsError:
                if target.read_bytes() != content:
                    raise ResearchAgentOutputArtifactError(
                        "research Agent artifact hash collision or corruption"
                    ) from None
        finally:
            if temporary.exists():
                temporary.unlink()

    def _assert_safe_path(self, target: Path) -> None:
        if target.parent.resolve(strict=True) != self._blob_root.resolve(strict=True):
            raise ResearchAgentOutputArtifactError(
                "research Agent artifact path escaped its owned root"
            )
