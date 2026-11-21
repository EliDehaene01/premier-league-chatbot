"""Azure AI Content Safety Prompt Shields on retrieved chunks, before they reach the model.

Fails closed: if the service errors, every chunk is dropped and the caller is told retrieval is
unavailable, rather than passing unchecked text to the model.
"""

import logging
from dataclasses import dataclass, field
from time import sleep

import httpx

from backend.config import Settings, settings
from backend.observability import tracing

log = logging.getLogger(__name__)
API_VERSION = "2024-09-01"
# service limits per call (checked 2026-11-21): at most 5 documents, 10,000 characters in total
MAX_DOCS = 5
MAX_CHARS = 9500
# the free tier allows a burst of about 5 calls, then answers 429 with Retry-After: 1; a news
# digest needs more batches than that, so a 429 waits and retries the same batch
RETRIES_ON_429 = 3
MAX_WAIT_S = 10.0


@dataclass
class ShieldResult:
    safe: list[dict] = field(default_factory=list)
    flagged: list[dict] = field(default_factory=list)
    error: str | None = None


def _batches(chunks: list[dict]):
    batch, size = [], 0
    for c in chunks:
        if batch and (len(batch) == MAX_DOCS or size + len(c["text"][:MAX_CHARS]) > MAX_CHARS):
            yield batch
            batch, size = [], 0
        batch.append(c)
        size += len(c["text"][:MAX_CHARS])
    if batch:
        yield batch


def _retry_after(resp, attempt: int) -> float:
    try:
        wait = float(resp.headers.get("Retry-After", ""))
    except ValueError:
        wait = 2.0**attempt
    return min(max(wait, 0.5), MAX_WAIT_S)


def shield(chunks: list[dict], query: str, cfg: Settings = settings, http=None) -> ShieldResult:
    if not chunks:
        return ShieldResult()
    with tracing.observe(
        "prompt_shields", as_type="guardrail", input={"chunks": len(chunks)}
    ) as span:
        result = _shield(chunks, query, cfg, http)
        level = {"level": "WARNING"} if result.error or result.flagged else {}
        span.update(
            output={
                "safe": len(result.safe),
                "flagged": len(result.flagged),
                "error": result.error,
            },
            **level,
        )
    return result


def _shield(chunks: list[dict], query: str, cfg: Settings, http) -> ShieldResult:
    url = cfg.content_safety_endpoint.rstrip("/") + "/contentsafety/text:shieldPrompt"
    headers = {"Ocp-Apim-Subscription-Key": cfg.content_safety_api_key}
    http = http or httpx.Client(timeout=15)
    result = ShieldResult()
    try:
        for batch in _batches(chunks):
            body = {"userPrompt": query[:1000], "documents": [c["text"][:MAX_CHARS] for c in batch]}
            for attempt in range(RETRIES_ON_429 + 1):
                resp = http.post(
                    url, params={"api-version": API_VERSION}, headers=headers, json=body
                )
                if resp.status_code != 429 or attempt == RETRIES_ON_429:
                    break
                sleep(_retry_after(resp, attempt))
            resp.raise_for_status()  # still 429 after the retries: fail closed below
            analysis = resp.json()["documentsAnalysis"]
            for chunk, verdict in zip(batch, analysis, strict=True):
                (result.flagged if verdict["attackDetected"] else result.safe).append(chunk)
    except Exception as e:  # fail closed on any error, including a malformed response
        log.warning("Prompt Shields failed, dropping %d chunks: %s", len(chunks), e)
        return ShieldResult(error=f"Prompt Shields unavailable: {type(e).__name__}")
    for c in result.flagged:
        log.warning("Prompt Shields flagged article %s chunk; dropped", c.get("article_id"))
    return result
