"""Facts for the Friday news highlights: the week's articles grouped into stories and ranked.

Articles are grouped by embedding similarity (the mean of each article's chunk vectors from the
RAG index). The model labels each story's type; the importance score is computed here from fixed
weights in weights.yaml, so the same week always ranks the same way.
"""

import math
from datetime import datetime, timedelta

import psycopg
from psycopg.rows import dict_row

STORY_TYPES = (
    "title_race",
    "relegation_race",
    "manager_change",
    "injury_key_player",
    "suspension",
    "transfer",
    "record",
    "award",
    "match_preview",
    "match_reaction",
    "other",
)


def week_articles(conn: psycopg.Connection, end: datetime, cfg: dict) -> list[dict]:
    """Articles published in the window before `end`, with their mean chunk embedding."""
    start = end - timedelta(days=cfg.get("window_days", 7))
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT a.content_id, a.title, a.description, a.published_at, a.club_ids, a.tags,
                   a.body_text, avg(c.embedding)::text AS embedding
            FROM silver.articles a
            LEFT JOIN silver.article_chunks c USING (content_id)
            WHERE a.published_at > %s AND a.published_at <= %s AND (%s OR NOT a.is_fantasy)
            GROUP BY a.content_id
            ORDER BY a.published_at DESC
            """,
            (start, end, cfg.get("include_fantasy", False)),
        ).fetchall()
    for r in rows:
        r["embedding"] = parse_vector(r["embedding"])
    return rows


def parse_vector(text: str | None) -> list[float] | None:
    return [float(x) for x in text.strip("[]").split(",")] if text else None


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def cluster(articles: list[dict], threshold: float) -> list[list[dict]]:
    """Greedy single pass, newest first: an article joins the story whose centroid it is most
    similar to, if that similarity reaches `threshold`; otherwise it starts a new story.
    Articles without an embedding (not indexed yet) stand alone."""
    stories: list[dict] = []
    for a in articles:
        best, best_sim = None, threshold
        if a["embedding"]:
            for s in stories:
                if s["centroid"] and (sim := cosine(a["embedding"], s["centroid"])) >= best_sim:
                    best, best_sim = s, sim
        if best is None:
            stories.append({"articles": [a], "centroid": a["embedding"]})
        else:
            n = len(best["articles"])
            best["centroid"] = [
                (c * n + x) / (n + 1) for c, x in zip(best["centroid"], a["embedding"], strict=True)
            ]
            best["articles"].append(a)
    return [s["articles"] for s in stories]


def importance(story: list[dict], story_type: str, now: datetime, cfg: dict) -> float:
    w = cfg["score"]
    newest = max(a["published_at"] for a in story)
    age_days = max((now - newest).total_seconds() / 86400, 0)
    recency = 0.5 ** (age_days / cfg.get("recency_half_life_days", 3))
    return round(
        w["coverage"] * math.log(1 + len(story))
        + w["type"].get(story_type, 0)
        + w["recency"] * recency,
        4,
    )


def story_brief(i: int, story: list[dict]) -> dict:
    """What the labelling call sees: titles and descriptions only, never article bodies."""
    return {
        "story": i,
        "articles": [{"title": a["title"], "description": a["description"]} for a in story[:5]],
    }


def rank(stories: list[list[dict]], labels: dict[int, str], now: datetime, cfg: dict) -> list[dict]:
    ranked = []
    for i, story in enumerate(stories):
        story_type = labels.get(i, "other")
        if story_type not in STORY_TYPES:
            story_type = "other"
        ranked.append(
            {
                "story": i,
                "type": story_type,
                "articles": story,
                "score": importance(story, story_type, now, cfg),
            }
        )
    ranked.sort(
        key=lambda s: (-s["score"], -max(a["published_at"] for a in s["articles"]).timestamp())
    )
    return ranked[: cfg.get("stories", 7)]
