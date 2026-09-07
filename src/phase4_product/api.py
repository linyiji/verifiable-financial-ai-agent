"""Isolated FastAPI router for the frozen Phase 4 product surface.

The repository's central route and application bootstrap modules are Parent-owned.
This router can be registered there without moving product truth into FastAPI.
"""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from src.phase4_product.admission import DraftLeaseAuthorizationV1
from src.phase4_product.contracts import (
    PHASE4_CONTRACT_VERSION,
    AtomicRunProjectionV1,
    ClaimDetailV1,
    ConfirmResearchRunRequestV1,
    ConfirmRunResponseV1,
    CreateResearchObjectRequestV1,
    ExecutionRecordSurfaceV1,
    FinancialReviewSurfaceV1,
    PrepareResearchRunRequestV1,
    ReleasedObjectCoreV1,
    ReleasedResultProjectionV1,
    ReportArtifactGroupV1,
    ReportSurfaceV1,
    ResearchObjectCollectionV1,
    ResearchObjectDetailV1,
    ResearchRunDetailV1,
    ResearchRunDraftV1,
    ResearchRunHistoryCollectionV1,
    ResultsWorkspaceV1,
    TraceBundleV1,
)
from src.phase4_product.draft_review import ExactDraftReview, RenewDraftLeaseRequest
from src.phase4_product.errors import ProductError, product_error
from src.phase4_product.hashing import require_sha256_identity
from src.phase4_product.memory_contracts import MaterializeMemoryRequest, ResearchMemorySnapshot

CONTRACT_HEADER = "X-Phase4-Contract-Version"
JSON_MEDIA_TYPE = "application/json; charset=utf-8"
_JSON_REPRESENTATION = ("application/json; charset=utf-8",)
_ARTIFACT_REPRESENTATIONS = (
    "application/pdf",
    "text/html; charset=utf-8",
)
_ARTIFACT_CONTENT_PATH = "/api/research-runs/{run_id}/artifacts/{artifact_id}/content"
_EVENT_STREAM_PATH = "/api/research-runs/{run_id}/events"
_MEDIA_TOKEN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_Q_VALUE = re.compile(r"^(?:0(?:\.\d{0,3})?|1(?:\.0{0,3})?)$")


class Phase4JSONResponse(JSONResponse):
    """JSON response with the frozen explicit UTF-8 media type."""

    media_type = JSON_MEDIA_TYPE


def _parse_media_value(
    value: str,
    *,
    allow_wildcards: bool,
    allow_quality: bool,
) -> tuple[str, str, dict[str, str]]:
    """Parse the small, fail-closed media-type subset used by the frozen API."""

    segments = [segment.strip() for segment in value.split(";")]
    if not segments or not segments[0] or segments[0].count("/") != 1:
        raise ValueError("invalid media type")
    major, minor = (part.strip().lower() for part in segments[0].split("/", 1))
    if not major or not minor:
        raise ValueError("invalid media type")
    if major == "*" and minor != "*":
        raise ValueError("invalid media wildcard")
    if not allow_wildcards and (major == "*" or minor == "*"):
        raise ValueError("media wildcards are not supported here")
    for token in (major, minor):
        if token != "*" and _MEDIA_TOKEN.fullmatch(token) is None:
            raise ValueError("invalid media token")

    parameters: dict[str, str] = {}
    for segment in segments[1:]:
        if not segment or "=" not in segment:
            raise ValueError("invalid media parameter")
        name, parameter_value = (part.strip() for part in segment.split("=", 1))
        name = name.lower()
        if not name or _MEDIA_TOKEN.fullmatch(name) is None or name in parameters:
            raise ValueError("invalid media parameter")
        if (
            len(parameter_value) >= 2
            and parameter_value.startswith('"')
            and parameter_value.endswith('"')
        ):
            parameter_value = parameter_value[1:-1]
        if not parameter_value or any(ord(character) < 0x20 for character in parameter_value):
            raise ValueError("invalid media parameter")
        if name == "q":
            if not allow_quality or _Q_VALUE.fullmatch(parameter_value) is None:
                raise ValueError("invalid media quality")
        parameters[name] = parameter_value.lower()
    return major, minor, parameters


def _media_range_precedence_and_quality(
    media_range: str,
    representation: str,
) -> tuple[int, int, int] | None:
    range_major, range_minor, range_parameters = _parse_media_value(
        media_range,
        allow_wildcards=True,
        allow_quality=True,
    )
    representation_major, representation_minor, representation_parameters = _parse_media_value(
        representation,
        allow_wildcards=False,
        allow_quality=False,
    )
    quality = range_parameters.pop("q", "1")
    if range_major not in {"*", representation_major}:
        return None
    if range_minor not in {"*", representation_minor}:
        return None
    if not all(
        representation_parameters.get(name) == value for name, value in range_parameters.items()
    ):
        return None
    whole, _, fraction = quality.partition(".")
    quality_thousandths = int(whole) * 1000 + int((fraction + "000")[:3])
    specificity = 0 if range_major == "*" else 1 if range_minor == "*" else 2
    return specificity, len(range_parameters), quality_thousandths


def _effective_representation_quality(
    media_ranges: list[str],
    representation: str,
) -> int:
    matches = tuple(
        match
        for media_range in media_ranges
        if (
            match := _media_range_precedence_and_quality(
                media_range,
                representation,
            )
        )
        is not None
    )
    if not matches:
        return 0
    highest_precedence = max(
        (specificity, parameter_count) for specificity, parameter_count, _ in matches
    )
    # Ambiguous duplicate ranges fail closed by honoring the lowest effective
    # quality at the highest specificity instead of letting order bypass q=0.
    return min(
        quality
        for specificity, parameter_count, quality in matches
        if (specificity, parameter_count) == highest_precedence
    )


def _require_acceptable_response_media(
    request: Request,
    representations: tuple[str, ...],
) -> None:
    values = request.headers.getlist("Accept")
    if not values:
        return
    ranges = [part.strip() for value in values for part in value.split(",")]
    try:
        if not ranges or not all(ranges):
            raise ValueError("empty media range")
        for media_range in ranges:
            _parse_media_value(
                media_range,
                allow_wildcards=True,
                allow_quality=True,
            )
        accepted = any(
            _effective_representation_quality(ranges, representation) > 0
            for representation in representations
        )
    except ValueError:
        accepted = False
    if not accepted:
        raise product_error(
            "SCHEMA_INCOMPATIBLE",
            "unsupported response media type",
        )


def _require_json_request_media(request: Request) -> None:
    values = request.headers.getlist("Content-Type")
    accepted = False
    if len(values) == 1:
        try:
            major, minor, parameters = _parse_media_value(
                values[0],
                allow_wildcards=False,
                allow_quality=False,
            )
            accepted = (
                (major, minor) == ("application", "json")
                and set(parameters) <= {"charset"}
                and parameters.get("charset", "utf-8") == "utf-8"
            )
        except ValueError:
            accepted = False
    if not accepted:
        raise product_error(
            "SCHEMA_INCOMPATIBLE",
            "unsupported request media type",
        )


class Phase4NegotiatedRoute(APIRoute):
    """Perform version and media negotiation before FastAPI reads a body."""

    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        route_handler = super().get_route_handler()
        if self.path == _ARTIFACT_CONTENT_PATH:
            representations = _ARTIFACT_REPRESENTATIONS
        elif self.path == _EVENT_STREAM_PATH:
            representations = ("text/event-stream",)
        else:
            representations = _JSON_REPRESENTATION

        async def negotiated_route_handler(request: Request) -> Response:
            # Contract selection is the first transport gate, including when
            # media headers and the request body are invalid at the same time.
            _select_contract(request)
            _require_acceptable_response_media(request, representations)
            if request.method == "POST":
                _require_json_request_media(request)
            return await route_handler(request)

        return negotiated_route_handler


@dataclass(frozen=True, slots=True)
class VerifiedArtifactBytes:
    """Bytes already resolved from trusted storage and bound to durable metadata."""

    run_id: str
    artifact_id: str
    content: bytes
    content_type: str
    sha256: str
    filename: str
    disposition: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.run_id, str)
            or not self.run_id.strip()
            or not isinstance(self.artifact_id, str)
            or not self.artifact_id.strip()
        ):
            raise ValueError("artifact byte identity must not be blank")
        if not isinstance(self.content, bytes):
            raise ValueError("artifact content must be immutable bytes")
        if self.content_type not in {"text/html; charset=utf-8", "application/pdf"}:
            raise ValueError("artifact content type is not allowlisted")
        if self.disposition not in {"inline", "attachment"}:
            raise ValueError("artifact disposition is not allowlisted")
        if self.filename not in {"report.html", "report.pdf"}:
            raise ValueError("artifact filename is not allowlisted")
        expected_delivery = {
            "text/html; charset=utf-8": ("report.html", "inline"),
            "application/pdf": ("report.pdf", "attachment"),
        }[self.content_type]
        if (self.filename, self.disposition) != expected_delivery:
            raise ValueError("artifact delivery metadata does not match its representation")
        if len(self.content) == 0:
            raise ValueError("available artifact bytes must not be empty")
        require_sha256_identity(self.sha256, field_name="artifact SHA-256")


class Phase4ProductBackend(Protocol):
    async def create_object(
        self,
        payload: CreateResearchObjectRequestV1,
        *,
        idempotency_key: str,
        request_id: str | None,
    ) -> ResearchObjectDetailV1: ...

    async def list_objects(
        self,
        *,
        symbol: str | None,
        query: str | None,
        cursor: str | None,
        limit: int,
    ) -> ResearchObjectCollectionV1: ...

    async def get_object(self, object_id: str) -> ResearchObjectDetailV1: ...

    async def get_memory(self, object_id: str) -> ResearchMemorySnapshot: ...

    async def materialize_memory(
        self, object_id: str, source_run_id: str
    ) -> ResearchMemorySnapshot: ...

    async def list_runs(
        self,
        *,
        object_id: str | None,
        statuses: tuple[str, ...],
        result_availability: str | None,
        cursor: str | None,
        limit: int,
    ) -> ResearchRunHistoryCollectionV1: ...

    async def list_object_runs(
        self,
        object_id: str,
        *,
        cursor: str | None,
        limit: int,
    ) -> ResearchRunHistoryCollectionV1: ...

    async def prepare_run(
        self,
        payload: PrepareResearchRunRequestV1,
        *,
        idempotency_key: str,
        request_id: str | None,
    ) -> ResearchRunDraftV1: ...

    async def confirm_run(
        self,
        payload: ConfirmResearchRunRequestV1,
        *,
        idempotency_key: str,
        request_id: str | None,
    ) -> ConfirmRunResponseV1: ...

    async def get_run(self, run_id: str) -> ResearchRunDetailV1: ...

    async def get_projection(self, run_id: str) -> AtomicRunProjectionV1: ...

    async def get_results(self, run_id: str) -> ResultsWorkspaceV1: ...

    async def get_result(self, run_id: str) -> ReleasedResultProjectionV1: ...

    async def get_report(self, run_id: str) -> ReportSurfaceV1: ...

    async def get_claim(self, run_id: str, claim_id: str) -> ClaimDetailV1: ...

    async def get_review(self, run_id: str) -> FinancialReviewSurfaceV1: ...

    async def get_execution(
        self,
        run_id: str,
        *,
        cursor: str | None,
        limit: int,
        event_types: tuple[str, ...],
        task_id: str | None,
        query: str | None,
    ) -> ExecutionRecordSurfaceV1: ...

    async def get_trace(self, run_id: str, claim_id: str) -> TraceBundleV1: ...

    async def get_artifacts(self, run_id: str) -> ReportArtifactGroupV1: ...

    async def get_artifact_content(
        self,
        run_id: str,
        artifact_id: str,
    ) -> VerifiedArtifactBytes: ...

    async def get_released_object(self, object_id: str) -> ReleasedObjectCoreV1: ...


def _backend(request: Request) -> Phase4ProductBackend:
    try:
        return request.app.state.phase4_product_backend
    except AttributeError as exc:
        raise product_error(
            "TRANSIENT_BACKEND_ERROR",
            "product backend is temporarily unavailable",
        ) from exc


def _request_id(request: Request) -> str | None:
    # The frozen field is server-issued. Never echo a caller-supplied header as
    # authority or let it become an error-detail injection channel.
    value = getattr(request.state, "request_id", None)
    if not isinstance(value, str) or not value.strip():
        return None
    if len(value) > 256 or any(ord(character) < 0x20 for character in value):
        return None
    return value


def _select_contract(request: Request) -> str:
    values = request.headers.getlist(CONTRACT_HEADER)
    selected = PHASE4_CONTRACT_VERSION
    if values:
        if len(values) != 1 or values[0] != PHASE4_CONTRACT_VERSION or "," in values[0]:
            raise product_error(
                "SCHEMA_INCOMPATIBLE",
                "unsupported Phase 4 contract version",
                details={"supported_version": PHASE4_CONTRACT_VERSION},
            )
        selected = values[0]
    return selected


def _admit_contract(request: Request, response: Response) -> str:
    selected = _select_contract(request)
    response.headers[CONTRACT_HEADER] = selected
    return selected


def _require_exact_run_response(run_id: str, value: object, resource_type: str):
    """Reject a self-consistent foreign response before FastAPI serializes it."""

    if getattr(value, "run_id", None) != run_id:
        raise product_error(
            "IDENTITY_MISMATCH",
            f"{resource_type} does not belong to the requested exact Run",
            resource_type=resource_type,
            resource_id=run_id,
        )
    return value


def _idempotency_key(request: Request) -> str:
    values = request.headers.getlist("Idempotency-Key")
    if len(values) != 1 or not values[0].strip():
        raise product_error(
            "REQUEST_VALIDATION_ERROR",
            "one non-empty Idempotency-Key header is required",
            details={"field": "Idempotency-Key"},
        )
    return values[0]


def create_phase4_product_router() -> APIRouter:
    router = APIRouter(
        prefix="/api",
        dependencies=[],
        default_response_class=Phase4JSONResponse,
        route_class=Phase4NegotiatedRoute,
    )

    @router.post("/objects", response_model=ResearchObjectDetailV1, status_code=201)
    async def create_object(
        payload: CreateResearchObjectRequestV1,
        request: Request,
        response: Response,
    ) -> ResearchObjectDetailV1:
        _admit_contract(request, response)
        return await _backend(request).create_object(
            payload,
            idempotency_key=_idempotency_key(request),
            request_id=_request_id(request),
        )

    @router.get("/objects", response_model=ResearchObjectCollectionV1)
    async def list_objects(
        request: Request,
        response: Response,
        symbol: str | None = None,
        query: str | None = None,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> ResearchObjectCollectionV1:
        _admit_contract(request, response)
        return await _backend(request).list_objects(
            symbol=symbol,
            query=query,
            cursor=cursor,
            limit=limit,
        )

    @router.get("/objects/{object_id}", response_model=ResearchObjectDetailV1)
    async def get_object(
        object_id: str,
        request: Request,
        response: Response,
    ) -> ResearchObjectDetailV1:
        _admit_contract(request, response)
        return await _backend(request).get_object(object_id)

    @router.get("/objects/{object_id}/memory", response_model=ResearchMemorySnapshot)
    async def get_memory(object_id: str, request: Request, response: Response):
        _admit_contract(request, response)
        return await _backend(request).get_memory(object_id)

    @router.post("/objects/{object_id}/memory/materialize", response_model=ResearchMemorySnapshot)
    async def materialize_memory(
        object_id: str, payload: MaterializeMemoryRequest, request: Request, response: Response
    ):
        _admit_contract(request, response)
        return await _backend(request).materialize_memory(object_id, payload.source_run_id)

    @router.get("/objects/{object_id}/runs", response_model=ResearchRunHistoryCollectionV1)
    async def list_object_runs(
        object_id: str,
        request: Request,
        response: Response,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> ResearchRunHistoryCollectionV1:
        _admit_contract(request, response)
        return await _backend(request).list_object_runs(
            object_id,
            cursor=cursor,
            limit=limit,
        )

    @router.get("/objects/{object_id}/released-state", response_model=ReleasedObjectCoreV1)
    async def get_released_object(
        object_id: str,
        request: Request,
        response: Response,
    ) -> ReleasedObjectCoreV1:
        _admit_contract(request, response)
        return await _backend(request).get_released_object(object_id)

    @router.get("/research-runs", response_model=ResearchRunHistoryCollectionV1)
    async def list_runs(
        request: Request,
        response: Response,
        object_id: str | None = None,
        status: tuple[str, ...] = Query(default=()),
        result_availability: str | None = None,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> ResearchRunHistoryCollectionV1:
        _admit_contract(request, response)
        return await _backend(request).list_runs(
            object_id=object_id,
            statuses=status,
            result_availability=result_availability,
            cursor=cursor,
            limit=limit,
        )

    @router.get("/research-drafts/{draft_id}", response_model=ExactDraftReview)
    async def read_draft_review(draft_id: str, request: Request, response: Response):
        _admit_contract(request, response)
        return await _backend(request).read_draft_review(draft_id)

    @router.post(
        "/research-drafts/{draft_id}/lease-renewals", response_model=DraftLeaseAuthorizationV1
    )
    async def renew_draft_lease(
        draft_id: str, payload: RenewDraftLeaseRequest, request: Request, response: Response
    ):
        _admit_contract(request, response)
        return await _backend(request).renew_draft_lease(
            draft_id, payload, idempotency_key=_idempotency_key(request)
        )

    @router.post("/research-runs/prepare", response_model=ResearchRunDraftV1)
    async def prepare_run(
        payload: PrepareResearchRunRequestV1,
        request: Request,
        response: Response,
    ) -> ResearchRunDraftV1:
        _admit_contract(request, response)
        response.status_code = 201
        return await _backend(request).prepare_run(
            payload,
            idempotency_key=_idempotency_key(request),
            request_id=_request_id(request),
        )

    @router.post("/research-runs", response_model=ConfirmRunResponseV1)
    async def confirm_run(
        payload: ConfirmResearchRunRequestV1,
        request: Request,
        response: Response,
    ) -> ConfirmRunResponseV1:
        _admit_contract(request, response)
        result = await _backend(request).confirm_run(
            payload,
            idempotency_key=_idempotency_key(request),
            request_id=_request_id(request),
        )
        response.status_code = 200 if result.response_meta.idempotency_replayed else 201
        return result

    @router.get("/research-runs/{run_id}", response_model=ResearchRunDetailV1)
    async def get_run(
        run_id: str,
        request: Request,
        response: Response,
    ) -> ResearchRunDetailV1:
        _admit_contract(request, response)
        return await _backend(request).get_run(run_id)

    @router.get("/research-runs/{run_id}/projection", response_model=AtomicRunProjectionV1)
    async def get_projection(
        run_id: str,
        request: Request,
        response: Response,
    ) -> AtomicRunProjectionV1:
        _admit_contract(request, response)
        result = await _backend(request).get_projection(run_id)
        response.headers["ETag"] = (
            f'"p4:{run_id}:{result.projection_revision}:{result.projection_sequence}"'
        )
        return result

    @router.get("/research-runs/{run_id}/results", response_model=ResultsWorkspaceV1)
    async def get_results(
        run_id: str,
        request: Request,
        response: Response,
    ) -> ResultsWorkspaceV1:
        _admit_contract(request, response)
        result = await _backend(request).get_results(run_id)
        return _require_exact_run_response(run_id, result, "results_workspace")

    @router.get("/research-runs/{run_id}/result", response_model=ReleasedResultProjectionV1)
    async def get_result(
        run_id: str,
        request: Request,
        response: Response,
    ) -> ReleasedResultProjectionV1:
        _admit_contract(request, response)
        result = await _backend(request).get_result(run_id)
        return _require_exact_run_response(run_id, result, "released_result")

    @router.get("/research-runs/{run_id}/report-view", response_model=ReportSurfaceV1)
    async def get_report(
        run_id: str,
        request: Request,
        response: Response,
    ) -> ReportSurfaceV1:
        _admit_contract(request, response)
        result = await _backend(request).get_report(run_id)
        return _require_exact_run_response(run_id, result, "report")

    @router.get(
        "/research-runs/{run_id}/claims/{claim_id}",
        response_model=ClaimDetailV1,
    )
    async def get_claim(
        run_id: str,
        claim_id: str,
        request: Request,
        response: Response,
    ) -> ClaimDetailV1:
        _admit_contract(request, response)
        return await _backend(request).get_claim(run_id, claim_id)

    @router.get(
        "/research-runs/{run_id}/review-view",
        response_model=FinancialReviewSurfaceV1,
    )
    async def get_review(
        run_id: str,
        request: Request,
        response: Response,
    ) -> FinancialReviewSurfaceV1:
        _admit_contract(request, response)
        result = await _backend(request).get_review(run_id)
        return _require_exact_run_response(run_id, result, "review")

    @router.get(
        "/research-runs/{run_id}/execution-view",
        response_model=ExecutionRecordSurfaceV1,
    )
    async def get_execution(
        run_id: str,
        request: Request,
        response: Response,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        type: tuple[str, ...] = Query(default=()),
        task_id: str | None = None,
        query: str | None = None,
    ) -> ExecutionRecordSurfaceV1:
        _admit_contract(request, response)
        result = await _backend(request).get_execution(
            run_id,
            cursor=cursor,
            limit=limit,
            event_types=type,
            task_id=task_id,
            query=query,
        )
        return _require_exact_run_response(run_id, result, "canonical_execution")

    @router.get("/research-runs/{run_id}/trace/{claim_id}", response_model=TraceBundleV1)
    async def get_trace(
        run_id: str,
        claim_id: str,
        request: Request,
        response: Response,
    ) -> TraceBundleV1:
        _admit_contract(request, response)
        return await _backend(request).get_trace(run_id, claim_id)

    @router.get("/research-runs/{run_id}/artifacts", response_model=ReportArtifactGroupV1)
    async def get_artifacts(
        run_id: str,
        request: Request,
        response: Response,
    ) -> ReportArtifactGroupV1:
        _admit_contract(request, response)
        return await _backend(request).get_artifacts(run_id)

    @router.get("/research-runs/{run_id}/artifacts/{artifact_id}/content")
    async def get_artifact_content(
        run_id: str,
        artifact_id: str,
        request: Request,
        response: Response,
    ) -> Response:
        _admit_contract(request, response)
        if "range" in request.headers:
            raise product_error(
                "REQUEST_VALIDATION_ERROR",
                "Range requests are not supported for report artifacts",
                details={"reason_code": "RANGE_NOT_SUPPORTED"},
            )
        artifact = await _backend(request).get_artifact_content(run_id, artifact_id)
        if artifact.run_id != run_id or artifact.artifact_id != artifact_id:
            raise product_error(
                "IDENTITY_MISMATCH",
                "report artifact does not belong to the exact requested resource",
                resource_type="report_artifact",
                resource_id=artifact_id,
            )
        _require_acceptable_response_media(request, (artifact.content_type,))
        digest = hashlib.sha256(artifact.content).hexdigest()
        if artifact.sha256 != f"sha256:{digest}":
            raise product_error(
                "INTEGRITY_FAILURE",
                "report artifact failed integrity verification",
                resource_type="report_artifact",
                resource_id=artifact_id,
            )
        raw_digest = base64.b64encode(bytes.fromhex(digest)).decode("ascii")
        return Response(
            content=artifact.content,
            media_type=artifact.content_type,
            headers={
                CONTRACT_HEADER: PHASE4_CONTRACT_VERSION,
                "Content-Length": str(len(artifact.content)),
                "Digest": f"sha-256={raw_digest}",
                "ETag": f'"sha256-{digest}"',
                "Content-Disposition": (f'{artifact.disposition}; filename="{artifact.filename}"'),
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router


def install_phase4_error_handlers(app: FastAPI) -> None:
    """Install the frozen error envelope at the Parent composition boundary."""

    @app.exception_handler(ProductError)
    async def product_error_handler(request: Request, exc: ProductError) -> JSONResponse:
        envelope = exc.envelope(request_id=_request_id(request))
        return Phase4JSONResponse(
            status_code=exc.status_code,
            content=envelope.model_dump(mode="json"),
            headers={CONTRACT_HEADER: PHASE4_CONTRACT_VERSION},
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        # FastAPI may reject body/query values before entering a route. Keep
        # version negotiation authoritative over that validation path.
        try:
            _select_contract(request)
        except ProductError as version_error:
            return Phase4JSONResponse(
                status_code=version_error.status_code,
                content=version_error.envelope(request_id=_request_id(request)).model_dump(
                    mode="json"
                ),
                headers={CONTRACT_HEADER: PHASE4_CONTRACT_VERSION},
            )
        safe_errors = [
            {
                "location": [str(part) for part in error.get("loc", ())],
                "type": str(error.get("type", "validation_error")),
            }
            for error in exc.errors()
        ]
        error = product_error(
            "REQUEST_VALIDATION_ERROR",
            "request validation failed",
            details={"errors": safe_errors},
        )
        return Phase4JSONResponse(
            status_code=error.status_code,
            content=error.envelope(request_id=_request_id(request)).model_dump(mode="json"),
            headers={CONTRACT_HEADER: PHASE4_CONTRACT_VERSION},
        )

    @app.exception_handler(Exception)
    async def internal_error_handler(request: Request, _exc: Exception) -> JSONResponse:
        # Exception text is deliberately omitted: it may contain SQL, stack
        # paths, provider payloads, credentials, prompts, or hidden reasoning.
        error = product_error("INTERNAL_ERROR", "an internal product error occurred")
        return Phase4JSONResponse(
            status_code=error.status_code,
            content=error.envelope(request_id=_request_id(request)).model_dump(mode="json"),
            headers={CONTRACT_HEADER: PHASE4_CONTRACT_VERSION},
        )
