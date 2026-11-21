"""Split articles into overlapping chunks with a title/date/tags header."""

import hashlib
import json
from datetime import datetime

# ponytail: tokens estimated as words / 0.75 (English prose average); swap in a tokenizer
# if chunk sizes ever need to be exact.
WORDS_PER_TOKEN = 0.75
CHUNK_TOKENS = 400
OVERLAP_TOKENS = 50
CHUNKER_VERSION = 2  # bump when chunking changes, so build_index re-chunks everything
SKIP_TAG_PREFIXES = ("content-type:", "content-format:", "content-creator:")


def header(title: str, published_at: datetime | str | None, tags: list[str]) -> str:
    date = published_at.date().isoformat() if isinstance(published_at, datetime) else published_at
    labels = [t.split(":", 1)[-1] for t in tags if not t.startswith(SKIP_TAG_PREFIXES)]
    lines = [title, f"Published: {date or 'unknown'}"]
    if labels:
        lines.append("Tags: " + ", ".join(labels))
    return "\n".join(lines)


def content_hash(article: dict) -> str:
    fields = [CHUNKER_VERSION] + [article.get(k) for k in ("title", "published_at", "tags",
                                  "body_text", "description", "summary")]  # fmt: skip
    return hashlib.sha256(json.dumps(fields, default=str).encode()).hexdigest()


def split_text(text: str, chunk_tokens: int = CHUNK_TOKENS, overlap: int = OVERLAP_TOKENS):
    """Greedy paragraph packing up to ~chunk_tokens; long paragraphs are split on words.

    Each chunk after the first starts with the last ~overlap tokens of the previous one.
    """
    max_words = int(chunk_tokens * WORDS_PER_TOKEN)
    overlap_words = int(overlap * WORDS_PER_TOKEN)
    pieces: list[list[str]] = []
    for para in (p for p in text.split("\n") if p.strip()):
        words = para.split()
        while len(words) > max_words:  # a paragraph longer than a chunk
            pieces.append(words[:max_words])
            words = words[max_words - overlap_words :]
        pieces.append(words)

    def n_words(ws: list[str]) -> int:  # "\n" marks a paragraph break, not a word
        return sum(w != "\n" for w in ws)

    chunks: list[list[str]] = []
    current: list[str] = []
    for words in pieces:
        if current and n_words(current) + len(words) > max_words:
            chunks.append(current)
            real = [w for w in current if w != "\n"]
            current = real[-overlap_words:] if overlap_words else []
        if current:
            current = current + ["\n"]
        current = current + words
    if current:
        chunks.append(current)
    return [" ".join(c).replace(" \n ", "\n").strip() for c in chunks]


def chunk_article(article: dict) -> list[str]:
    """Header + body chunks; an article without body text becomes one short chunk."""
    head = header(article["title"], article.get("published_at"), article.get("tags") or [])
    body = article.get("body_text")
    if not body:
        rest = [article.get("description"), article.get("summary")]
        parts = list(dict.fromkeys(p.strip() for p in rest if p and p.strip()))  # dedupe
        return [head + ("\n\n" + "\n".join(parts) if parts else "")]
    return [f"{head}\n\n{chunk}" for chunk in split_text(body)]
