"""Azure AI Content Safety Prompt Shields on retrieved chunks, before they reach the model.

Fails closed: if the service errors, every chunk is dropped and the caller is told retrieval is
unavailable, rather than passing unchecked text to the model.
"""

import logging
from dataclasses import dataclass, field

import httpx

from backend.config import Settings, settings

log = logging.getLogger(__name__)
API_VERSION = "2024-09-01"
# service limits per call (checked 2026-11-21): at most 5 documents, 10,000 characters in total
MAX_DOCS = 5
MAX_CHARS = 9500


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


def shield(chunks: list[dict], query: str, cfg: Settings = settings, http=None) -> ShieldResult:
    if not chunks:
        return ShieldResult()
    url = cfg.content_safety_endpoint.rstrip("/") + "/contentsafety/text:shieldPrompt"
    headers = {"Ocp-Apim-Subscription-Key": cfg.content_safety_api_key}
    http = http or httpx.Client(timeout=15)
    result = ShieldResult()
    try:
        for batch in _batches(chunks):
            resp = http.post(
                url,
                params={"api-version": API_VERSION},
                headers=headers,
                json={
                    "userPrompt": query[:1000],
                    "documents": [c["text"][:MAX_CHARS] for c in batch],
                },
            )
            resp.raise_for_status()
            analysis = resp.json()["documentsAnalysis"]
            for chunk, verdict in zip(batch, analysis, strict=True):
                (result.flagged if verdict["attackDetected"] else result.safe).append(chunk)
    except Exception as e:  # fail closed on any error, including a malformed response
        log.warning("Prompt Shields failed, dropping %d chunks: %s", len(chunks), e)
        return ShieldResult(error=f"Prompt Shields unavailable: {type(e).__name__}")
    for c in result.flagged:
        log.warning("Prompt Shields flagged article %s chunk; dropped", c.get("article_id"))
    return result
