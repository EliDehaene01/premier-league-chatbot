from backend.llm.providers import LLMProvider

BATCH_SIZE = 64


def embed_texts(provider: LLMProvider, texts: list[str], purpose: str = "build_index"):
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        vectors.extend(provider.embed(texts[i : i + BATCH_SIZE], purpose=purpose))
    return vectors
