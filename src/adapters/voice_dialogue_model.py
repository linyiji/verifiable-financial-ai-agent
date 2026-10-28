"""Ordinary voice latency settings only; research clients keep their routing/options."""

import asyncio
import hashlib
import json
import re
import time

import httpx
from pydantic import ValidationError

from src.adapters.llm.provider import (
    LLMFailureClassification,
    LLMProviderUnavailableError,
    LLMRequestError,
    LLMStructuredResponse,
    StructuredOutputError,
)
from src.adapters.llm.teamorouter import TeamoRouterClient


def structured_json_hint(response_model) -> str:
    """Keep the supplier instruction aligned with this endpoint's validated schema."""
    schema = response_model.model_json_schema()
    fields = schema["properties"]
    constraint_fields = []
    if "constraints" in fields:
        definition = fields["constraints"]["items"]["$ref"].rsplit("/", 1)[-1]
        constraint_fields = list(schema["$defs"][definition]["properties"])
    if 'intents' in fields or 'plan_id' in fields:
        return '只输出符合以下JSON Schema的对象，不增加字段；256 token以内。JSON模式不代替应用校验。'+json.dumps(schema,ensure_ascii=False,separators=(',',':'))
    if 'updates' in fields:
        return ('输出完整JSON，按此顺序写齐五个字段：revision、next、updates、kind、text。revision为当前任务revision；next必填且只能ANSWER/ASK_MONTH/ASK_FOLLOWUP/SUMMARIZE/CLOSE，摘要也必须写next；updates每项field为month或followup，value及evidence为当前用户依据，evidence必须保留current_utterance原字形（勿转繁体），未谈及用[]。kind为answer或clarification。text是自然回应。不要添加其他字段。全部JSON在256 token内，先保证五字段完整，再简洁表达。')
    kind = fields["kind"]
    allowed = kind.get("enum") or [kind["const"]]
    maximum = fields["text"]["maxLength"]
    return (
        '只输出一个JSON对象，恰好含' + '、'.join(fields) + '字段。kind只能是'
        + '、'.join(allowed)
        + f'之一；text是1到{maximum}字的回答。'
        + ('constraints每项必须含' + '、'.join(constraint_fields) + '；没有指示时为空数组。'
           if 'constraints' in fields else '示例JSON：' + json.dumps({'kind': allowed[0], 'text': '整理资料与发出申请是两回事。'}, ensure_ascii=False))
    )


class DeepSeekVoiceDialogueModel:
    """Official DeepSeek JSON Output, with one attempt and a shared HTTP pool."""

    provider_name = "deepseek_official"

    def request_body(self, messages, response_model):
        return {
            "model": self.settings.model,
            "messages": [{"role":m.role,"content":m.content + structured_json_hint(response_model)
                          if m.role=="system" else m.content} for m in messages],
            "response_format":{"type":"json_object"},"max_tokens":256,
            "thinking":{"type":"disabled"},
        }

    def request_headers(self):
        return {"Authorization":"Bearer "+self.settings.api_key.get_secret_value(),
                "Content-Type":"application/json","Accept":"application/json"}

    def __init__(self, settings, client: httpx.AsyncClient, *, observer=None):
        if settings.provider != "deepseek_official" or not settings.enabled:
            raise LLMRequestError("Official voice provider is not configured")
        if settings.model_deadline_seconds > 5 or settings.dialogue_deadline_seconds > 8:
            raise LLMRequestError("Voice deadlines exceed product limits")
        self.settings = settings
        self.client = client
        self.observer = observer

    def request_deadline_seconds(self):
        """Product default; protocol adapters may derive an earlier/later
        remaining budget from their own externally enforced absolute contract.
        """
        return self.settings.model_deadline_seconds

    async def complete_structured(self, *, messages, response_model, schema_name,
                                  force_fallback=False):
        if force_fallback:
            raise LLMRequestError("Voice fallback is disabled")
        started = time.monotonic()
        model = self.settings.model
        row = {"requested_model": model, "schema_name": schema_name,
               "request_id": None, "http_status": None, "raw_content": None,
               "raw_usage": None, "response_model": None, "finish_reason": None,
               "stage": "request", "outcome": "UNKNOWN"}
        body = self.request_body(messages, response_model)
        try:
            async with asyncio.timeout(self.request_deadline_seconds()):
                row["stage"] = "http"
                request = self.client.build_request("POST",
                    self.settings.base_url.rstrip("/") + "/chat/completions",
                    json=body,
                    headers=self.request_headers(),
                )
                if self.observer:
                    async def observe_transport(event_name, information):
                        # httpcore stage names only: never socket objects,
                        # authentication headers or request contents.
                        row.setdefault("transport_events", []).append({
                            "stage": event_name,
                            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                        })
                    request.extensions["trace"] = observe_transport
                row["request_body_sha256"] = hashlib.sha256(request.content).hexdigest()
                row["request_bytes"] = len(request.content)
                if self.observer:
                    row["request_body"] = body
                from src.adapters.voice_call_budget import charge
                charge("LLM", self.provider_name, model)
                response = await self.client.send(request, stream=True)
                try:
                    row["http_status"] = response.status_code
                    row["request_id"] = response.headers.get("x-request-id")
                    row["headers_ms"] = round((time.monotonic() - started) * 1000, 3)
                    row["stage"] = "body"
                    raw = await response.aread()
                    row["body_complete_ms"] = round((time.monotonic() - started) * 1000, 3)
                    if self.observer:
                        row["response_body"] = raw.decode("utf-8", errors="replace")
                    if response.is_error:
                        def safe_error(value, limit):
                            text = str(value or 'UNKNOWN').replace(self.settings.api_key.get_secret_value(), '[REDACTED]')
                            text = re.sub(r'(?:https?|wss?)://\S+|(?i:bearer\s+)\S+', '[REDACTED]', text)
                            text = re.sub(r'[A-Za-z0-9+/=_-]{80,}', '[REDACTED_BLOB]', text)
                            return text[:limit]
                        try:
                            error = json.loads(raw).get('error', {})
                            row['provider_error'] = {k:safe_error(error.get(k), n) for k,n in [('code',128),('type',128),('message',512)]}
                        except (ValueError, AttributeError, TypeError):
                            row['provider_error'] = {'code':'UNKNOWN','message':'NON_JSON_OR_UNEXPECTED_BODY_OMITTED'}
                        raise LLMRequestError(
                            "Official voice provider rejected request: "
                            f"HTTP {response.status_code}",
                            requested_model=model, attempted_models=(model,),
                            failure_classification=LLMFailureClassification.REQUEST_REJECTED,
                        )
                finally:
                    await response.aclose()
                row["stage"] = "outer_json"
                envelope = json.loads(raw)
                row["request_id"] = row["request_id"] or envelope.get("id")
                row["response_model"] = envelope.get("model")
                row["raw_usage"] = envelope.get("usage")
                row["stage"] = "content_extract"
                choice = envelope["choices"][0]
                row["finish_reason"] = choice.get("finish_reason")
                message = choice["message"]
                # Preserve an incomplete answer for diagnosis, never for delivery.
                row["raw_content"] = message.get("content")
                row["parse_status"] = "NOT_PARSED"
                if row["finish_reason"] != "stop" or message.get("refusal"):
                    row["parse_status"] = "REJECTED_INCOMPLETE_OR_REFUSED"
                    raise StructuredOutputError(
                        "Official voice response was incomplete or refused",
                        requested_model=model, attempted_models=(model,),
                        failure_classification=LLMFailureClassification.STRUCTURED_OUTPUT_INVALID,
                    )
                row["stage"] = "inner_json"
                decoded = json.loads(row["raw_content"])
                row["stage"] = "strict_schema"
                output = response_model.model_validate(decoded, strict=True)
                row["parse_status"] = "VALID"
                row["outcome"] = "VALID"
                return LLMStructuredResponse(
                    output=output, provider=self.provider_name, requested_model=model,
                    actual_model=row["response_model"] or model,
                    attempted_models=(model,), request_id=row["request_id"],
                    input_tokens=(row["raw_usage"] or {}).get("prompt_tokens"),
                    output_tokens=(row["raw_usage"] or {}).get("completion_tokens"),
                )
        except asyncio.CancelledError:
            row["outcome"] = "CANCELLED"
            raise
        except TimeoutError:
            row["outcome"] = "TIMEOUT"
            raise
        except httpx.HTTPError as exc:
            row["outcome"] = type(exc).__name__
            row["transport_error_type"] = type(exc).__name__
            row["last_transport_stage"] = (row.get("transport_events") or [{}])[-1].get("stage", "UNKNOWN")
            raise LLMProviderUnavailableError(
                "Official voice provider transport failed", requested_model=model,
                attempted_models=(model,),
                failure_classification=LLMFailureClassification.RETRYABLE_TRANSPORT_FAILURE,
            ) from exc
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValidationError) as exc:
            row["outcome"] = type(exc).__name__
            row["parse_status"] = "INVALID_AT_" + row["stage"].upper()
            raise StructuredOutputError(
                "Official voice response failed strict validation",
                requested_model=model, attempted_models=(model,),
                failure_classification=LLMFailureClassification.STRUCTURED_OUTPUT_INVALID,
            ) from exc
        except Exception as exc:
            row["outcome"] = type(exc).__name__
            raise
        finally:
            row["validation_complete_ms"] = round((time.monotonic() - started) * 1000, 3)
            from src.adapters.voice_call_budget import capture_model
            capture_model(row)
            if self.observer:
                self.observer(row)


class CandidateVoiceDialogueModel(DeepSeekVoiceDialogueModel):
    """Provider protocol mapping behind the existing structured reply contract."""

    def __init__(self, settings, client, *, observer=None):
        allowed={
            'qwen_beijing':('https://dashscope.aliyuncs.com/compatible-mode/v1',
                {'qwen3.7-flash-2026-07-15','qwen3.7-plus-2026-05-26'}),
            'mimo_official':('https://api.xiaomimimo.com/v1',
                {'mimo-v2.6-flash','mimo-v2.6-pro'}),
        }
        route=allowed.get(settings.provider)
        if (not route or not settings.enabled or settings.base_url.rstrip('/')!=route[0]
                or settings.model not in route[1]
                or settings.model_deadline_seconds>5 or settings.dialogue_deadline_seconds>8):
            raise LLMRequestError('Voice candidate capability/configuration mismatch')
        self.provider_name=settings.provider
        self.settings,self.client,self.observer=settings,client,observer

    def request_body(self, messages, response_model):
        body=super().request_body(messages,response_model)
        if self.provider_name=='qwen_beijing':
            body.pop('thinking');body['enable_thinking']=False
        elif self.provider_name=='mimo_official':
            body['max_completion_tokens']=body.pop('max_tokens')
        return body

    def request_headers(self):
        if self.provider_name=='mimo_official':
            return {'api-key':self.settings.api_key.get_secret_value(),
                    'Content-Type':'application/json','Accept':'application/json'}
        return super().request_headers()


def configured_voice_dialogue_model(settings, client, *, observer=None):
    implementation=DeepSeekVoiceDialogueModel if settings.provider=='deepseek_official' else CandidateVoiceDialogueModel
    return implementation(settings,client,observer=observer)


class VoiceDialogueModel(TeamoRouterClient):
    def __init__(self, settings, *, timeout_seconds=5.0, trace=None,
                 disable_unavailable_fallback=False, **kwargs):
        if disable_unavailable_fallback:
            # Voice-only routing fence while the configured backup has no channel.
            # Research requests retain the original settings and fallback route.
            settings = settings.model_copy(update={"fallback_model": settings.primary_model})
        super().__init__(
            settings,
            timeout_seconds=timeout_seconds,
            retry_routing_resource_unavailable=True,
            **kwargs,
        )
        self._trace = trace

    async def _send(self, *, request_template, **kwargs):
        from time import monotonic

        started = monotonic()
        model = kwargs.get("model")
        try:
            result = await super()._send(
                request_template={
                    **request_template,
                    "reasoning_effort": "none",
                    "max_completion_tokens": 256,
                },
                **kwargs,
            )
            if self._trace:
                self._trace(
                    "provider_attempt", model=model,
                    elapsed_ms=round((monotonic()-started)*1000), outcome="ok",
                )
            return result
        except BaseException as exc:
            if self._trace:
                self._trace(
                    "provider_attempt", model=model,
                    elapsed_ms=round((monotonic()-started)*1000), outcome=type(exc).__name__,
                )
            raise
