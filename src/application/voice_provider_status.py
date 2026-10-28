"""Explicit operator-observed supplier status, separate from RTC/control health.

This reader makes no network or model calls. Only a verified observation should
update the configured file; selecting a provider does not establish availability.
"""

import json
import os
from pathlib import Path

from contracts.api.voice_session import VoiceProviderAvailability


def voice_provider_availability() -> VoiceProviderAvailability:
    path = os.getenv("VEFIN_VOICE_PROVIDER_STATUS_FILE")
    unknown = dict(provider="unknown", state="unknown", blocked=bool(path),
                   reason="NOT_VERIFIED", message="语音供应商可用性尚未确认。")
    if not path:
        return VoiceProviderAvailability(**unknown)

    try:
        raw = json.loads(Path(path).read_text())
        provider = raw["provider"]
        state = raw["state"]
        if provider not in {"quickrouter", "mimo"} or state not in {"available", "unavailable"}:
            raise ValueError("Invalid observation")
        reason = raw["reason"]
        if reason not in {"UPSTREAM_CONNECT_TIMEOUT", "VERIFIED_TTS", "UPSTREAM_UNAVAILABLE", "SINGLE_SEGMENT_ONLY", "PRODUCT_CHAIN_INCOMPLETE", "PRODUCT_QUALITY_PENDING"}:
            raise ValueError("Invalid reason")
        if (state == "available") != (reason == "VERIFIED_TTS"):
            raise ValueError("Inconsistent observation")
        name = {"quickrouter": "QuickRouter", "mimo": "MiMo"}[provider]
        message = (f"本轮语音链路已完成；识别及答复质量仍未通过，普通连续会话暂不开放。"
                   if reason == "PRODUCT_QUALITY_PENDING" else
                   f"{name} 全文音频已交付；产品语音识别超时，连续对话暂不可用。"
                   if reason == "PRODUCT_CHAIN_INCOMPLETE" else
                   f"{name} 已完成单段测试；连续对话尚未验收，普通会话暂不开放。"
                   if reason == "SINGLE_SEGMENT_ONLY" else
                   f"当前语音供应商 {name} 不可用：TLS 连接超时。"
                   if reason == "UPSTREAM_CONNECT_TIMEOUT" else
                   f"当前语音供应商 {name} 不可用。" if state == "unavailable" else
                   f"语音供应商 {name} 最近一次合成验证通过；不代表当前质量验收。")
        return VoiceProviderAvailability(provider=provider, state=state,
            blocked=state != "available", reason=reason, message=message,
            checked_at=raw["checked_at"])
    except (OSError, ValueError, KeyError, TypeError):
        # Never return raw file contents or an exception that may contain secrets.
        return VoiceProviderAvailability(**unknown)


def local_test_admitted(user: str, *, key=None, session_id=None) -> bool:
    """One operator-scoped local regression, without opening ordinary sessions."""
    from datetime import datetime, UTC
    if os.getenv("VEFIN_VOICE_AUTH_MODE") != "local":
        return False
    path = os.getenv("VEFIN_VOICE_TEST_ADMISSION_FILE")
    if not path:
        return False
    try:
        data = json.loads(Path(path).read_text())
        return (data.get("enabled") is True and data["user"] == user
                and datetime.fromisoformat(data["expires_at"]) > datetime.now(UTC)
                and ((key is not None and data["idempotency_key"] == key)
                     or (session_id is not None and data.get("session_id") == session_id)))
    except (OSError, ValueError, TypeError, KeyError):
        return False
