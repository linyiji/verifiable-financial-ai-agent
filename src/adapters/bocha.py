"""Bocha discovery followed by bounded, separately authenticated original-source reads.

Search text is never an accepted financial number or a complete transcript.
V1 trusts only explicitly configured official publishers; unknown dates fail closed.
"""

from datetime import UTC, datetime
from hashlib import sha256
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

import httpx

from src.data.capability_policy import CAPABILITIES, DataOutcome
from src.data.provider import RawProviderSnapshot
from src.phase4_product.hashing import canonical_json_sha256


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data.strip())


class BochaDiscovery:
    def __init__(self, api_key, *, transport=None, official_domains=None):
        self._key = api_key
        self._transport = transport
        self.domains = official_domains or {
            "NVDA": ("investor.nvidia.com", "nvidianews.nvidia.com", "www.sec.gov")
        }

    async def acquire(self, request, capability):
        if "bocha" not in CAPABILITIES.get(capability, ()):
            return (), DataOutcome.FAILED, "CAPABILITY_NOT_AUTHORIZED"
        if not self._key or not self._key.get_secret_value():
            return (), DataOutcome.UNAVAILABLE_PROVIDER, "NOT_CONFIGURED"
        if request.symbol not in self.domains:
            return (), DataOutcome.UNAVAILABLE_PROVIDER, "SOURCE_AUTHORITY_UNCONFIGURED"
        suffix = (
            "earnings call transcript"
            if capability == "earnings_transcript"
            else "company investor news"
        )
        query = f"{request.symbol} {suffix} {request.expected_period or request.as_of.isoformat()}"
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=20, follow_redirects=False
            ) as client:
                response = await client.post(
                    "https://api.bocha.cn/v1/web-search",
                    headers={"Authorization": "Bearer " + self._key.get_secret_value()},
                    json={"query": query, "summary": False, "count": 5},
                )
                if response.status_code != 200:
                    return (
                        (),
                        (
                            DataOutcome.UNAVAILABLE_ENTITLEMENT
                            if response.status_code in {401, 402, 403}
                            else DataOutcome.UNAVAILABLE_PROVIDER
                        ),
                        "HTTP_" + str(response.status_code),
                    )
                body = response.json()
                if not isinstance(body, dict):
                    return (), DataOutcome.FAILED, "INVALID_RESPONSE"
                if body.get("code", 200) != 200:
                    return (), DataOutcome.UNAVAILABLE_PROVIDER, "PROVIDER_DECLINED"
                data = body.get("data", body)
                if not isinstance(data, dict) or not isinstance(data.get("webPages", {}), dict):
                    return (), DataOutcome.FAILED, "INVALID_RESPONSE"
                pages = data.get("webPages", {}).get("value", [])
                if not isinstance(pages, list):
                    return (), DataOutcome.FAILED, "INVALID_RESPONSE"
                snapshots, seen = [], set()
                for page in pages[:5]:
                    if not isinstance(page, dict):
                        continue
                    url = page.get("url", "")
                    if not isinstance(url, str):
                        continue
                    parts = urlsplit(url)
                    if (
                        parts.scheme != "https"
                        or parts.hostname not in self.domains[request.symbol]
                        or parts.username
                        or parts.password
                        or parts.port not in {None, 443}
                    ):
                        continue
                    url = urlunsplit(
                        (parts.scheme, parts.netloc.lower(), parts.path, parts.query, "")
                    )
                    if url in seen:
                        continue
                    seen.add(url)
                    # Do not guess timezone semantics of legacy dateLastCrawled.
                    try:
                        published = datetime.fromisoformat(
                            page.get("datePublished", "").replace("Z", "+00:00")
                        )
                    except (ValueError, AttributeError):
                        continue
                    if published.tzinfo is None or published.date() > request.as_of:
                        continue
                    age = (request.as_of - published.date()).days
                    if age > (550 if capability == "earnings_transcript" else 7):
                        continue
                    async with client.stream("GET", url) as original:
                        if original.status_code != 200 or "text/html" not in original.headers.get(
                            "content-type", ""
                        ):
                            continue
                        chunks, size = [], 0
                        async for chunk in original.aiter_bytes():
                            size += len(chunk)
                            if size > 1_000_000:
                                break
                            chunks.append(chunk)
                        if size > 1_000_000:
                            continue
                    content = b"".join(chunks).decode("utf-8", errors="replace")
                    if self._key.get_secret_value() in content:
                        continue
                    parser = _Text()
                    parser.feed(content)
                    text = " ".join(filter(None, parser.parts))
                    issuer = "NVIDIA" if request.symbol == "NVDA" else request.symbol
                    if len(text) < 200 or issuer.casefold() not in text.casefold():
                        continue
                    payload = {
                        "discovery_provider": "bocha",
                        "original_url": url,
                        "authority": "PRIMARY" if parts.hostname == "www.sec.gov" else "OFFICIAL",
                        "content_scope": "TRANSCRIPT_DISCOVERY_ONLY"
                        if capability == "earnings_transcript"
                        else "ORIGINAL_DOCUMENT",
                        "datePublished": published.isoformat(),
                        "content_sha256": sha256(content.encode()).hexdigest(),
                        "content": content,
                    }
                    digest = canonical_json_sha256(payload)
                    snapshots.append(
                        RawProviderSnapshot(
                            provider="bocha",
                            source_locator=url,
                            retrieved_at=datetime.now(UTC),
                            raw_artifact_ref="retained-original:" + digest,
                            snapshot_hash=digest.removeprefix("sha256:"),
                            raw_payload=payload,
                            records=[
                                {
                                    "document_authority": {
                                        k: payload[k]
                                        for k in (
                                            "discovery_provider",
                                            "original_url",
                                            "authority",
                                            "content_sha256",
                                            "content_scope",
                                        )
                                    },
                                    "field": "official_document_text",
                                    "value": text[:16000],
                                    "unit": "TEXT",
                                    "period": "DOCUMENT",
                                    "as_of": published.date().isoformat(),
                                }
                            ],
                        )
                    )
                snapshots.sort(
                    key=lambda s: (
                        s.raw_payload["authority"] != "PRIMARY",
                        -datetime.fromisoformat(s.raw_payload["datePublished"]).timestamp(),
                        s.source_locator,
                    )
                )
                return (
                    tuple(snapshots),
                    (
                        DataOutcome.PARTIAL
                        if snapshots and capability == "earnings_transcript"
                        else DataOutcome.AVAILABLE
                        if snapshots
                        else DataOutcome.INSUFFICIENT_DATA
                    ),
                    (None if snapshots else "NO_VERIFIED_ORIGINAL"),
                )
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return (), DataOutcome.UNAVAILABLE_PROVIDER, "DISCOVERY_OR_SOURCE_UNAVAILABLE"
