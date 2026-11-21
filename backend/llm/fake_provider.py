"""A scripted LLMProvider for tests: replays chat results, embeds by word hashing. No network."""

import hashlib
import math

from backend.llm.providers import ChatResult, ToolCall

DIM = 1536


def word_vector(text: str) -> list[float]:
    """Bag-of-words hashed into DIM buckets, L2-normalised: texts sharing words are close."""
    v = [0.0] * DIM
    for word in text.lower().split():
        v[int(hashlib.md5(word.strip(".,!?:;").encode()).hexdigest(), 16) % DIM] += 1.0
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


class FakeProvider:
    def __init__(self, script: list[ChatResult] | None = None):
        self.script = list(script or [])
        self.chat_calls: list[dict] = []
        self.prompt_version = None

    def chat(self, messages, tools=None, purpose="chat", response_format=None) -> ChatResult:
        self.chat_calls.append(
            {"messages": list(messages), "tools": tools, "purpose": purpose,
             "response_format": response_format}
        )  # fmt: skip
        return self.script.pop(0)

    def chat_stream(self, messages, tools=None, on_delta=None, purpose="chat") -> ChatResult:
        result = self.chat(messages, tools, purpose)
        for word in (result.content or "").split():  # replay the answer word by word
            if on_delta:
                on_delta(word + " ")
        return result

    def embed(self, texts, purpose="embedding"):
        return [word_vector(t) for t in texts]


def call(name: str, arguments: str = "{}", id_: str = "c1") -> ToolCall:
    return ToolCall(id_, name, arguments)
