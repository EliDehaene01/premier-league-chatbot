"""Turns gathered facts into a stored digest: structured LLM output, validated against the facts.

The model writes prose only. Every bullet must cite source_ids from the facts; a bullet whose
sources are unknown, or that states a number or score its sources do not contain, is dropped,
and the drops are recorded on the digest. Citations are renumbered [1], [2], ... and resolved to
title, date and URL from the database, as in the chat (backend/llm/citations.py).
"""

import json
import re
from datetime import UTC, datetime

import psycopg
from psycopg.types.json import Jsonb

from backend.llm import citations
from backend.llm.grounding import numbers, numbers_in_data
from backend.llm.providers import LLMProvider
from backend.prompts import load_named
from backend.rag.shields import shield
from digests import news, recap

RECAP_PROMPT, LABEL_PROMPT, STORY_PROMPT, NEWS_PROMPT = (
    "digest_recap_v1",
    "digest_label_v1",
    "digest_story_v1",
    "digest_news_v1",
)
# table-zone claims the model gets wrong when it misreads previous_position -> position; each
# is checked against what code computed for the matchweek (recap.gather's table facts)
ZONE_CLAIMS = [
    (
        "left_bottom3",
        r"\b(left|out of|escaped?|climb\w* out of|moved out of|lifted \w+ out of)\b"
        r"[^.;]{0,20}\b(bottom (three|3)|relegation zone)",
    ),
    (
        "entered_bottom3",
        r"\b(into|entered|enters?|dropped into|fell into|slipped into|sank into)"
        r"\b[^.;]{0,12}\b(bottom (three|3)|relegation zone)",
    ),
    (
        "left_top4",
        r"\b(out of|dropped out of|fell out of|left|slipped out of)\b[^.;]{0,12}"
        r"\btop (four|4)\b",
    ),
    (
        "entered_top4",
        r"\b(into|entered|enters?|crack\w*|broke into|moved into|climbed into)\b"
        r"[^.;]{0,12}\btop (four|4)\b",
    ),
    ("stayed_bottom", r"\b(stay\w*|remain\w*|still)\b[^.;]{0,12}\bbottom\b(?! (three|3|half))"),
    ("went_bottom", r"\b(dropped|fell|slipped|sank|went) to (the )?bottom\b(?! (three|3|half))"),
]
ZONE_RES = [(k, re.compile(p, re.I)) for k, p in ZONE_CLAIMS]
EXTRA_ALIASES = {
    "Manchester United": ["Man United"],
    "Tottenham Hotspur": ["Tottenham"],
    "Brighton and Hove Albion": ["Brighton & Hove Albion"],
    "Nottingham Forest": ["Nottm Forest"],
}
SCORE = re.compile(r"(?<![\d-])(\d{1,2})-(\d{1,2})(?![\d-])")
TEXT_PER_ARTICLE = 3000


class DigestError(Exception):
    pass


# ---------- JSON schemas for structured output (strict mode: every field required)


def _obj(**props) -> dict:
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


STR = {"type": "string"}
CITED = _obj(text=STR, sources={"type": "array", "items": STR})
RECAP_SCHEMA = _obj(
    headline=STR,
    intro=CITED,
    sections={"type": "array", "items": _obj(title=STR, bullets={"type": "array", "items": CITED})},
)
STORY_SCHEMA = _obj(title=STR, summary=CITED, bullets={"type": "array", "items": CITED})
NEWS_SCHEMA = _obj(headline=STR, intro=CITED)
LABEL_SCHEMA = _obj(
    labels={
        "type": "array",
        "items": _obj(
            story={"type": "integer"}, type={"type": "string", "enum": list(news.STORY_TYPES)}
        ),
    }
)


def _format(name: str, schema: dict) -> dict:
    return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}


class Writer:
    def __init__(self, conn: psycopg.Connection, provider: LLMProvider, shield_fn=shield):
        self.conn, self.provider, self.shield = conn, provider, shield_fn
        self.cost: float | None = 0.0

    def ask(self, prompt: str, payload, name: str, schema: dict) -> dict:
        result = self.provider.chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, default=str)},
            ],
            purpose=f"digest:{name}",
            response_format=_format(name, schema),
        )
        if self.cost is not None:
            self.cost = None if result.cost_usd is None else self.cost + result.cost_usd
        try:
            return json.loads(result.content or "")
        except json.JSONDecodeError as e:
            raise DigestError(f"{name}: the model did not return JSON") from e


# ---------- validation


def check_cited(
    item: dict, index: dict[str, object], base: set[str], drops: list[dict], where: str
) -> dict | None:
    """Keep `item` ({text, sources}) only if its sources are known and back its numbers."""
    text = item.get("text", "").strip()
    sources = list(dict.fromkeys(s for s in item.get("sources", []) if s in index))
    reason = None
    if not text:
        reason = "empty"
    elif not sources:
        reason = f"no valid source ({item.get('sources')})"
    else:
        backed = numbers_in_data([index[s] for s in sources]) | base
        loose = sorted(numbers(text) - backed, key=float)
        scores = {m.group(0) for m in SCORE.finditer(text)}
        known_scores = {str(index[s].get("score")) for s in sources if isinstance(index[s], dict)}
        known_scores |= {"-".join(reversed(k.split("-"))) for k in known_scores if "-" in k}
        bad_scores = sorted(s for s in scores if known_scores - {"None"} and s not in known_scores)
        if loose:
            reason = f"numbers not in its sources: {loose}"
        elif bad_scores:
            reason = f"scores not in its sources: {bad_scores}"
    if reason:
        drops.append({"where": where, "text": text, "reason": reason})
        return None
    return {"text": text, "sources": sources}


def club_aliases(conn) -> dict[str, list[str]]:
    rows = conn.execute("SELECT name, short_name FROM silver.clubs").fetchall()
    return {n: [n, *([sn] if sn else []), *EXTRA_ALIASES.get(n, [])] for n, sn in rows}


def zone_claim_error(text: str, table: dict, aliases: dict[str, list[str]]) -> str | None:
    """A claim that a club entered, left or stayed in a table zone must name a club that did."""
    rows = table.get("rows", [])
    if not rows:
        return None
    last = max(r["position"] for r in rows)
    allowed = {
        "left_bottom3": table.get("left_bottom3", []),
        "entered_bottom3": table.get("entered_bottom3", []),
        "left_top4": table.get("left_top4", []),
        "entered_top4": table.get("entered_top4", []),
        "stayed_bottom": [
            r["club"] for r in rows if r["position"] == last and r.get("previous_position") == last
        ],
        "went_bottom": [
            r["club"] for r in rows if r["position"] == last and r.get("previous_position") != last
        ],
    }

    def named(club: str) -> bool:
        return any(re.search(rf"\b{re.escape(a)}\b", text, re.I) for a in aliases.get(club, [club]))

    for kind, pattern in ZONE_RES:
        if pattern.search(text) and not any(named(c) for c in allowed[kind]):
            return f"table claim '{kind}' names none of {allowed[kind] or 'no club'}"
    return None


def number_sources(conn, items: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Resolve the cited ids in order of first use, as [{n, id, kind, title, date, url}]."""
    order: dict[str, int] = {}
    sources = []
    for it in items:
        for sid in it["sources"]:
            if sid not in order and (rec := citations.resolve(conn, sid)):
                order[sid] = len(order) + 1
                sources.append({"n": order[sid], "id": sid, **rec})
    return sources, order


def _store(
    conn,
    kind: str,
    period_key: str,
    facts: dict,
    doc: dict,
    sources: list[dict],
    checks: dict,
    prompt_version: str,
    cost: float | None,
) -> int:
    return conn.execute(
        "INSERT INTO digests (kind, period_key, period_start, period_end, headline, content, "
        "sources, facts, checks, prompt_version, cost_usd) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (
            kind,
            period_key,
            facts.get("period_start"),
            facts.get("period_end"),
            doc["headline"],
            Jsonb({k: v for k, v in doc.items() if k != "headline"}),
            Jsonb(sources),
            Jsonb(facts),
            Jsonb(checks),
            prompt_version,
            cost,
        ),
    ).fetchone()[0]


# ---------- matchweek recap


def recap_index(facts: dict) -> dict[str, object]:
    index: dict[str, object] = {}
    for f in facts["results"] + facts["catch_up_results"] + facts["pending_fixtures"]:
        index[f["source_id"]] = f
    index[facts["table"]["source_id"]] = facts["table"]
    if facts["top_scorers"]["source_id"]:
        index[facts["top_scorers"]["source_id"]] = facts["top_scorers"]
    return index


def results_section(facts: dict) -> dict:
    """The full results list, written by code from the data, never by the model."""

    def line(f: dict) -> str:
        goals = ", ".join(
            f"{g['player']} {g['minute']}'"
            + (
                " (og)"
                if g.get("type") == "OwnGoal"
                else " (pen)"
                if g.get("type") == "Penalty"
                else ""
            )
            for g in f["goals"]
        )
        return f"{f['home']} {f['score']} {f['away']}" + (f": {goals}" if goals else "")

    bullets = [{"text": line(f), "sources": [f["source_id"]]} for f in facts["results"]]
    bullets += [
        {"text": f"Catch-up, matchweek {f['matchweek']}: {line(f)}", "sources": [f["source_id"]]}
        for f in facts["catch_up_results"]
    ]
    bullets += [
        {"text": f"{p['home']} v {p['away']} is still to be played", "sources": [p["source_id"]]}
        for p in facts["pending_fixtures"]
    ]
    return {"title": "All results", "bullets": bullets, "generated_by": "code"}


def write_recap(
    conn,
    provider: LLMProvider,
    matchweek: int | None = None,
    now=None,
    cfg: dict | None = None,
    store: bool = True,
) -> dict:
    facts = recap.gather(conn, matchweek, now, cfg)
    if "error" in facts:
        raise DigestError(facts["error"])
    w = Writer(conn, provider)
    prompt = load_named(RECAP_PROMPT, season=facts["season"], matchweek=facts["matchweek"])
    index = recap_index(facts)
    base = {str(facts["matchweek"])} | numbers_in_data(facts["highlights"])
    aliases = club_aliases(conn)

    def check(item: dict, drops: list[dict], where: str) -> dict | None:
        kept = check_cited(item, index, base, drops, where)
        if kept and (why := zone_claim_error(kept["text"], facts["table"], aliases)):
            drops.append({"where": where, "text": kept["text"], "reason": why})
            return None
        return kept

    best = None
    for _attempt in range(2):  # one retry when the validator drops anything
        raw = w.ask(prompt, facts, "matchweek_recap", RECAP_SCHEMA)
        drops: list[dict] = []
        intro = check(raw["intro"], drops, "intro")
        sections = []
        for s in raw.get("sections", []):
            bullets = [
                b
                for i, x in enumerate(s.get("bullets", []))
                if (b := check(x, drops, f"{s.get('title')}[{i}]"))
            ]
            if bullets:
                sections.append({"title": s.get("title", "").strip(), "bullets": bullets})
        headline = raw.get("headline", "").strip()[:120]
        bad_zone = zone_claim_error(headline, facts["table"], aliases) if headline else None
        if not headline or numbers(headline) - numbers_in_data(facts) or bad_zone:
            reason = bad_zone or "ungrounded number"
            drops.append({"where": "headline", "text": headline, "reason": reason})
            headline = f"Matchweek {facts['matchweek']} recap"
        candidate = {"headline": headline, "intro": intro, "sections": sections, "drops": drops}
        if best is None or len(drops) < len(best["drops"]):
            best = candidate
        if not drops:
            break
    doc = {
        "headline": best["headline"],
        "intro": best["intro"],
        "sections": best["sections"] + [results_section(facts)],
    }
    return finish(
        conn,
        "matchweek_recap",
        f"mw{facts['matchweek']}",
        facts,
        doc,
        {"dropped": best["drops"], "attempts": _attempt + 1, **facts["checks"]},
        RECAP_PROMPT,
        w.cost,
        store,
    )


def finish(conn, kind, period_key, facts, doc, checks, prompt_version, cost, store) -> dict:
    items = ([doc["intro"]] if doc.get("intro") else []) + [
        b for s in doc["sections"] for b in s["bullets"]
    ]
    sources, order = number_sources(conn, items)
    for it in items:  # keep only ids that resolved, as numbers in source order
        it["cites"] = [order[s] for s in it["sources"] if s in order]
    digest = {
        "kind": kind,
        "period_key": period_key,
        **doc,
        "sources": sources,
        "checks": checks,
        "prompt_version": prompt_version,
        "cost_usd": cost,
        "created_at": datetime.now(UTC).isoformat(),
    }
    if store:
        digest["id"] = _store(
            conn, kind, period_key, facts, doc, sources, checks, prompt_version, cost
        )
    return digest


# ---------- news highlights


def write_news(
    conn,
    provider: LLMProvider,
    week_ending: datetime | None = None,
    cfg: dict | None = None,
    store: bool = True,
    shield_fn=shield,
) -> dict:
    cfg = cfg or {}
    end = week_ending or datetime.now(UTC)
    w = Writer(conn, provider, shield_fn)
    articles = news.week_articles(conn, end, cfg)
    if not articles:
        raise DigestError("no articles in the window")
    # every article's text passes Prompt Shields before any of it reaches the model
    docs = [
        {
            "content_id": a["content_id"],
            "text": "\n".join(
                filter(
                    None, [a["title"], a["description"], (a["body_text"] or "")[:TEXT_PER_ARTICLE]]
                )
            ),
        }
        for a in articles
    ]
    verdict = w.shield(docs, "Summarise this week's Premier League news")
    if verdict.error:
        raise DigestError(f"Prompt Shields unavailable, no digest written: {verdict.error}")
    safe = {d["content_id"] for d in verdict.safe}
    articles = [a for a in articles if a["content_id"] in safe]

    stories = news.cluster(articles, cfg.get("cluster_similarity", 0.8))
    briefs = [news.story_brief(i, s) for i, s in enumerate(stories)]
    labels = w.ask(
        load_named(LABEL_PROMPT, types=", ".join(news.STORY_TYPES)),
        briefs,
        "story_labels",
        LABEL_SCHEMA,
    )["labels"]
    top = news.rank(stories, {x["story"]: x["type"] for x in labels}, end, cfg)

    drops: list[dict] = []
    sections, summaries, index = [], [], {}
    for s in top:
        arts = s["articles"][: cfg.get("max_articles_per_story", 4)]
        payload = [
            {
                "source_id": f"a{a['content_id']}",
                "title": a["title"],
                "date": a["published_at"].date().isoformat(),
                "text": next(d["text"] for d in docs if d["content_id"] == a["content_id"]),
            }
            for a in arts
        ]
        story_index = {p["source_id"]: p for p in payload}
        index.update(story_index)
        raw = w.ask(load_named(STORY_PROMPT), payload, "news_story", STORY_SCHEMA)
        where = raw.get("title", "")[:40]
        summary = check_cited(raw["summary"], story_index, set(), drops, f"{where}: summary")
        bullets = [
            b
            for i, x in enumerate(raw.get("bullets", []))
            if (b := check_cited(x, story_index, set(), drops, f"{where}[{i}]"))
        ]
        if not summary:
            continue
        sections.append(
            {
                "title": raw.get("title", "").strip()[:100],
                "story_type": s["type"],
                "score": s["score"],
                "bullets": [summary, *bullets],
            }
        )
        summaries.append(
            {"title": raw.get("title"), "summary": summary["text"], "sources": summary["sources"]}
        )
    if not sections:
        raise DigestError("no story survived validation")

    week = end.date().isoformat()
    head = w.ask(load_named(NEWS_PROMPT, week_ending=week), summaries, "news_intro", NEWS_SCHEMA)
    intro = check_cited(head["intro"], index, set(), drops, "intro")
    headline = head.get("headline", "").strip()[:120] or f"News highlights, week ending {week}"
    if numbers(headline) - numbers_in_data(summaries):
        drops.append({"where": "headline", "text": headline, "reason": "ungrounded number"})
        headline = f"News highlights, week ending {week}"
    facts = {
        "period_start": min(a["published_at"] for a in articles).isoformat(),
        "period_end": end.isoformat(),
        "articles": len(articles),
        "flagged_by_shields": [f["content_id"] for f in verdict.flagged],
        "stories": [
            {
                "type": s["type"],
                "score": s["score"],
                "articles": [
                    {"source_id": f"a{a['content_id']}", "title": a["title"]} for a in s["articles"]
                ],
            }
            for s in top
        ],
    }
    doc = {"headline": headline, "intro": intro, "sections": sections}
    return finish(
        conn,
        "news_highlights",
        week,
        facts,
        doc,
        {"dropped": drops, "stories_found": len(stories)},
        f"{STORY_PROMPT}+{NEWS_PROMPT}",
        w.cost,
        store,
    )
