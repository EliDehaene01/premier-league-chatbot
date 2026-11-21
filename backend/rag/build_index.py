"""python -m backend.rag.build_index: embed new or changed articles into silver.article_chunks."""

import json
import sys

import psycopg
from psycopg.rows import dict_row

from backend.db import get_connection, init_db
from backend.llm.providers import AzureOpenAIProvider, LLMProvider
from backend.rag.chunking import chunk_article, content_hash
from backend.rag.embeddings import embed_texts

ARTICLES_PER_BATCH = 50


def to_vector(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def build_index(conn: psycopg.Connection, provider: LLMProvider) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        articles = cur.execute(
            "SELECT a.content_id, a.title, a.published_at, a.tags, a.body_text, a.description, "
            "a.summary, (SELECT content_hash FROM silver.article_chunks c "
            "            WHERE c.content_id = a.content_id LIMIT 1) AS indexed_hash "
            "FROM silver.articles a"
        ).fetchall()
    todo = [a for a in articles if a["indexed_hash"] != content_hash(a)]
    chunks_written = 0
    for i in range(0, len(todo), ARTICLES_PER_BATCH):
        batch = todo[i : i + ARTICLES_PER_BATCH]
        rows = [(a["content_id"], n, text, content_hash(a))
                for a in batch for n, text in enumerate(chunk_article(a))]  # fmt: skip
        vectors = embed_texts(provider, [r[2] for r in rows])
        with conn.transaction():
            conn.execute(
                "DELETE FROM silver.article_chunks WHERE content_id = ANY(%s)",
                ([a["content_id"] for a in batch],),
            )
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO silver.article_chunks "
                    "(content_id, chunk_index, text, content_hash, embedding) "
                    "VALUES (%s, %s, %s, %s, %s::vector)",
                    [(*r, to_vector(v)) for r, v in zip(rows, vectors, strict=True)],
                )
        chunks_written += len(rows)
    total = conn.execute("SELECT count(*) FROM silver.article_chunks").fetchone()[0]
    return {"articles": len(articles), "articles_indexed": len(todo),
            "chunks_written": chunks_written, "chunks_total": total}  # fmt: skip


def main() -> int:
    conn = get_connection()
    init_db(conn)
    print(json.dumps(build_index(conn, AzureOpenAIProvider(conn)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
