"""Hybrid search over silver.article_chunks: vector + full text, fused with RRF, recency-boosted."""

from datetime import UTC, date, datetime

import psycopg
from psycopg.rows import dict_row

from backend.config import settings
from backend.llm.providers import LLMProvider
from backend.rag.build_index import to_vector

CANDIDATES = 20  # per retriever
RRF_K = 60


def rrf_fuse(*rankings: list, k: int = RRF_K) -> dict:
    """Reciprocal rank fusion: score(id) = sum over rankings of 1 / (k + rank), rank from 1."""
    scores: dict = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return scores


def recency_weight(published_at: datetime | None, now: datetime, half_life_days: float) -> float:
    """1.0 for today, 0.75 after one half-life, tending to 0.5 for very old articles.

    final = rrf * (0.5 + 0.5 * decay): old but relevant articles still rank, fresh ones win ties.
    """
    if published_at is None:
        return 0.5
    age_days = max(0.0, (now - published_at).total_seconds() / 86400)
    return 0.5 + 0.5 * 0.5 ** (age_days / half_life_days)


def _filters(club_ids, date_from, date_to, exclude_fantasy) -> tuple[str, list]:
    where, params = [], []
    if club_ids:
        where.append("a.club_ids && %s::int[]")
        params.append(list(club_ids))
    if date_from:
        where.append("a.published_at >= %s")
        params.append(date_from)
    if date_to:
        where.append("a.published_at < %s::date + 1")
        params.append(date_to)
    if exclude_fantasy:
        where.append("NOT a.is_fantasy")
    return (" AND " + " AND ".join(where)) if where else "", params


def search(
    conn: psycopg.Connection,
    provider: LLMProvider,
    query: str,
    k: int = 5,
    club_ids: list[int] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    exclude_fantasy: bool = False,
    half_life_days: float | None = None,
    now: datetime | None = None,
) -> list[dict]:
    half_life = half_life_days or settings.recency_half_life_days
    now = now or datetime.now(UTC)
    where, params = _filters(club_ids, date_from, date_to, exclude_fantasy)
    vector = to_vector(provider.embed([query], purpose="retrieval")[0])
    base = "FROM silver.article_chunks c JOIN silver.articles a USING (content_id) WHERE true"
    with conn.cursor() as cur:
        by_vector = cur.execute(
            f"SELECT c.content_id, c.chunk_index {base}{where} "
            f"ORDER BY c.embedding <=> %s::vector LIMIT {CANDIDATES}",
            [*params, vector],
        ).fetchall()
        by_text = cur.execute(
            f"SELECT c.content_id, c.chunk_index {base}{where} "
            "AND c.tsv @@ websearch_to_tsquery('english', %s) "
            "ORDER BY ts_rank_cd(c.tsv, websearch_to_tsquery('english', %s)) DESC "
            f"LIMIT {CANDIDATES}",
            [*params, query, query],
        ).fetchall()
    fused = rrf_fuse(by_vector, by_text)
    if not fused:
        return []
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT c.content_id, c.chunk_index, c.text, a.title, a.published_at, "
            "a.canonical_url FROM silver.article_chunks c JOIN silver.articles a "
            "USING (content_id) WHERE (c.content_id, c.chunk_index) IN "
            "(SELECT * FROM unnest(%s::bigint[], %s::int[]))",
            ([key[0] for key in fused], [key[1] for key in fused]),
        ).fetchall()
    vec_rank = {key: r for r, key in enumerate(by_vector, start=1)}
    text_rank = {key: r for r, key in enumerate(by_text, start=1)}
    results = []
    for row in rows:
        key = (row["content_id"], row["chunk_index"])
        weight = recency_weight(row["published_at"], now, half_life)
        results.append({
            "article_id": row["content_id"],
            "title": row["title"],
            "date": row["published_at"].date().isoformat() if row["published_at"] else None,
            "url": row["canonical_url"],
            "text": row["text"],
            "scores": {"rrf": round(fused[key], 5), "recency": round(weight, 3),
                       "final": round(fused[key] * weight, 5),
                       "vector_rank": vec_rank.get(key), "text_rank": text_rank.get(key)},
        })  # fmt: skip
    results.sort(key=lambda r: r["scores"]["final"], reverse=True)
    return results[:k]
