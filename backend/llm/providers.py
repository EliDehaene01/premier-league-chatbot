"""LLM provider interface and the Azure OpenAI (Foundry) implementation."""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import psycopg
from openai import OpenAI

from backend.config import Settings, settings
from backend.observability.pricing import cost_usd


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON text, as the model wrote it


@dataclass
class ChatResult:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    cost_usd: float | None = None


class LLMProvider(Protocol):
    def chat(
        self, messages: list[dict], tools: list[dict] | None = None, purpose: str = "chat"
    ) -> ChatResult: ...

    def embed(self, texts: list[str], purpose: str = "embedding") -> list[list[float]]: ...


class AzureOpenAIProvider:
    """Azure OpenAI v1 API. Retries (429, 5xx, timeouts) use the SDK's exponential backoff.

    GPT-5 family deployments reject `temperature` and `max_tokens`, so neither is sent;
    `max_completion_tokens` caps the answer (reasoning tokens count toward it).
    """

    def __init__(
        self,
        conn: psycopg.Connection | None = None,
        cfg: Settings = settings,
        prompt_version: str | None = None,
        max_completion_tokens: int = 4000,
    ):
        base = cfg.azure_openai_endpoint.rstrip("/")
        if not base.endswith("/openai/v1"):
            base += "/openai/v1"
        self.client = OpenAI(base_url=base, api_key=cfg.azure_openai_api_key, max_retries=4)
        self.chat_deployment = cfg.azure_openai_chat_deployment
        self.embedding_deployment = cfg.azure_openai_embedding_deployment
        self.conn = conn
        self.prompt_version = prompt_version
        self.max_completion_tokens = max_completion_tokens

    def _record(self, kind, model, deployment, usage, started, purpose) -> float | None:
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        completion = getattr(usage, "completion_tokens", 0) or 0
        cost = cost_usd(model, prompt, completion)
        if self.conn is not None:
            self.conn.execute(
                "INSERT INTO llm_calls (kind, model, deployment, prompt_tokens, "
                "completion_tokens, latency_ms, cost_usd, prompt_version, purpose) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (kind, model, deployment, prompt, completion,
                 int((time.monotonic() - started) * 1000), cost, self.prompt_version, purpose),
            )  # fmt: skip
        return cost

    def chat(self, messages, tools=None, purpose="chat") -> ChatResult:
        started = time.monotonic()
        kwargs: dict[str, Any] = {"max_completion_tokens": self.max_completion_tokens}
        if tools:
            kwargs["tools"] = tools
        resp = self.client.chat.completions.create(
            model=self.chat_deployment, messages=messages, **kwargs
        )
        cost = self._record("chat", resp.model, self.chat_deployment, resp.usage, started, purpose)
        msg = resp.choices[0].message
        calls = [
            ToolCall(c.id, c.function.name, c.function.arguments) for c in msg.tool_calls or []
        ]
        return ChatResult(msg.content, calls, cost)

    def embed(self, texts, purpose="embedding") -> list[list[float]]:
        started = time.monotonic()
        resp = self.client.embeddings.create(model=self.embedding_deployment, input=texts)
        self._record("embedding", resp.model, self.embedding_deployment, resp.usage, started,
                     purpose)  # fmt: skip
        return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]


def tool_call_message(content: str | None, calls: list[ToolCall]) -> dict:
    """The assistant message that carries tool calls, in the chat completions wire format."""
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
            for c in calls
        ],
    }


def tool_result_message(call_id: str, result: Any) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": json.dumps(result, default=str)}
