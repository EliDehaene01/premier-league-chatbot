"""Tracing to self-hosted Langfuse (ADR 0005), and nothing at all when it is not configured.

One trace per chat turn, digest run or eval case. Inside it: a generation per LLM call (model,
tokens, cost, prompt version), a tool span per tool call (with how it was reached: MCP or
direct), a retriever span per news search and a guardrail span per Prompt Shields check.

Call sites use `observe(...)` and `turn(...)` as context managers and get back an object with
`update(...)`; when Langfuse is off, or the SDK fails, that object does nothing. Tracing must
never break an answer, so every SDK call is guarded.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Any

from backend.config import settings

log = logging.getLogger(__name__)
_client = None
_failed = False


class _Noop:
    id = None
    trace_id = None

    def update(self, **_):
        return self

    def __bool__(self):
        return False


NOOP = _Noop()


def enabled() -> bool:
    return (
        bool(
            settings.langfuse_host and settings.langfuse_public_key and settings.langfuse_secret_key
        )
        and not _failed
    )


def client():
    global _client, _failed
    if _client is None and enabled():
        try:
            from langfuse import Langfuse

            _client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                base_url=settings.langfuse_host,
                environment=settings.trace_environment,
                should_export_span=_ours,
            )
        except Exception as e:  # missing package, bad settings: run untraced
            _failed = True
            log.warning("tracing disabled: %s", e)
    return _client


def _ours(span) -> bool:
    """Export only our own observations: the MCP SDK's built-in OpenTelemetry spans would
    duplicate every tool call (ours carry input and output, theirs do not)."""
    scope = getattr(span, "instrumentation_scope", None)
    return getattr(scope, "name", "") == "langfuse-sdk"


class _Guarded:
    """Wraps a Langfuse observation so a failing update never reaches the caller."""

    def __init__(self, obs):
        self._obs = obs
        self.id = getattr(obs, "id", None)
        self.trace_id = getattr(obs, "trace_id", None)

    def update(self, **kw):
        try:
            self._obs.update(**kw)
        except Exception as e:
            log.debug("trace update failed: %s", e)
        return self

    def __bool__(self):
        return True


@contextmanager
def observe(name: str, as_type: str = "span", **kw) -> Iterator[Any]:
    """A span (or generation, tool, retriever, guardrail, agent) under the current one."""
    c = client()
    if c is None:
        yield NOOP
        return
    try:
        cm = c.start_as_current_observation(name=name, as_type=as_type, **kw)
        obs = cm.__enter__()
    except Exception as e:
        log.debug("trace start failed: %s", e)
        yield NOOP
        return
    try:
        yield _Guarded(obs)
    except BaseException as e:
        _safe_exit(cm, type(e), e, e.__traceback__)
        raise
    else:
        _safe_exit(cm, None, None, None)


def _safe_exit(cm, *exc) -> None:
    try:
        cm.__exit__(*exc)
    except Exception as e:
        log.debug("trace end failed: %s", e)


@contextmanager
def turn(
    name: str, session_id: str | None = None, tags: list[str] | None = None, **kw
) -> Iterator[Any]:
    """The root of one trace: a chat turn, a digest run, an eval case."""
    c = client()
    attrs = nullcontext()
    if c is not None:
        try:
            from langfuse import propagate_attributes

            attrs = propagate_attributes(session_id=session_id, tags=tags, trace_name=name)
        except Exception as e:
            log.debug("trace attributes failed: %s", e)
    with attrs, observe(name, as_type="agent", **kw) as obs:
        yield obs


# ---------- carrying a trace across the MCP boundary (W3C traceparent in the request _meta)


def traceparent() -> str | None:
    """The current observation as a W3C traceparent, to send with an MCP request."""
    c = client()
    if c is None:
        return None
    try:
        trace_id, span_id = c.get_current_trace_id(), c.get_current_observation_id()
    except Exception:
        return None
    if not trace_id or not span_id:
        return None
    return f"00-{trace_id}-{span_id}-01"


def parse_traceparent(value: Any) -> dict | None:
    """A Langfuse trace_context from a traceparent header, or None if it is not one."""
    if not isinstance(value, str):
        return None
    parts = value.split("-")
    if len(parts) != 4 or len(parts[1]) != 32 or len(parts[2]) != 16:
        return None
    try:
        int(parts[1], 16), int(parts[2], 16)
    except ValueError:
        return None
    return {"trace_id": parts[1], "parent_span_id": parts[2]}


def score(trace_id: str | None, name: str, value: float, comment: str | None = None) -> bool:
    """Attach a score (user feedback, an eval result) to a trace. False when not sent."""
    c = client()
    if c is None or not trace_id:
        return False
    try:
        c.create_score(trace_id=trace_id, name=name, value=value, comment=comment)
        return True
    except Exception as e:
        log.debug("score failed: %s", e)
        return False


def flush() -> None:
    if _client is not None:
        try:
            _client.flush()
        except Exception as e:
            log.debug("trace flush failed: %s", e)
