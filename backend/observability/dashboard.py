"""The AI Ops dashboard: cost, latency, quality and data freshness, as one static page.

Rendered into the GitHub Pages site (ops.html) every time the site is published, from the
local database. Aggregates only: no questions, answers, ids or keys ever reach the page.
Langfuse (local) is where single traces are inspected; this page is the public summary.
"""

import html
from datetime import UTC, datetime, timedelta

import psycopg
from psycopg.rows import dict_row

WINDOW_DAYS = 28
# what each llm_calls row was for, by its purpose prefix
AREA_SQL = """CASE
    WHEN purpose LIKE 'eval:%%' THEN 'Evals'
    WHEN purpose LIKE 'digest:%%' THEN 'Weekly digests'
    WHEN purpose LIKE 'mcp:%%' THEN 'MCP clients'
    WHEN purpose = 'build_index' THEN 'News index'
    ELSE 'Chat' END"""
STATUS_MARK = {"ok": "✓ OK", "warn": "! Warning", "fail": "✕ Failing"}


def _rows(conn, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def gather(conn: psycopg.Connection, now: datetime | None = None, days: int = WINDOW_DAYS) -> dict:
    now = now or datetime.now(UTC)
    since = now - timedelta(days=days)
    daily = {
        r["day"]: float(r["cost"] or 0)
        for r in _rows(
            conn,
            "SELECT (called_at AT TIME ZONE 'UTC')::date AS day, sum(cost_usd) AS cost "
            "FROM llm_calls WHERE called_at >= %s GROUP BY 1",
            (since,),
        )
    }
    first = (since + timedelta(days=1)).date()
    daily_cost = [
        {"day": first + timedelta(days=i), "cost": daily.get(first + timedelta(days=i), 0.0)}
        for i in range(days)
    ]
    by_area = _rows(
        conn,
        f"SELECT {AREA_SQL} AS area, count(*) AS calls, coalesce(sum(prompt_tokens), 0) "
        "AS prompt_tokens, coalesce(sum(completion_tokens), 0) AS completion_tokens, "
        "coalesce(sum(cost_usd), 0)::float AS cost FROM llm_calls WHERE called_at >= %s "
        "GROUP BY 1 ORDER BY cost DESC",
        (since,),
    )
    turns = _rows(
        conn,
        "SELECT count(*) AS turns, "
        "percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50, "
        "percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95, "
        "avg(cost_usd)::float AS cost_per_turn, count(*) FILTER (WHERE error IS NOT NULL) "
        "AS errors FROM chat_turns WHERE created_at >= %s",
        (since,),
    )[0]
    feedback = _rows(
        conn,
        "SELECT count(*) FILTER (WHERE rating = 'up') AS up, "
        "count(*) FILTER (WHERE rating = 'down') AS down, "
        "count(*) FILTER (WHERE review_outcome = 'promoted') AS promoted "
        "FROM feedback WHERE created_at >= %s",
        (since,),
    )[0]
    evals = _rows(
        conn,
        "SELECT run_at, dataset, subset, prompt_version, cases, pass_rate, cost_usd, "
        "latency_p50_ms, latency_p95_ms, passed_thresholds FROM public.eval_runs "
        "ORDER BY run_at DESC LIMIT 8",
    )
    freshness = _rows(
        conn,
        "SELECT DISTINCT ON (name) name, status, detail, checked_at "
        "FROM public.freshness_checks ORDER BY name, checked_at DESC",
    )
    return {
        "generated_at": now,
        "days": days,
        "total_cost": sum(d["cost"] for d in daily_cost),
        "daily_cost": daily_cost,
        "by_area": by_area,
        "turns": turns,
        "feedback": feedback,
        "evals": evals,
        "freshness": freshness,
    }


# ---------- rendering (plain HTML + inline SVG, styled by the site's CSS variables)

CSS = """
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px}
.tile b{display:block;font-size:24px;line-height:1.2;font-variant-numeric:tabular-nums}
.tile span{color:var(--muted);font-size:13px}
.chart{width:100%;height:auto;display:block}.chart .bar{fill:var(--accent)}
.chart .bar:hover{opacity:.75}.chart text{fill:var(--muted);font-size:11px}
.chart line{stroke:var(--line)}td.l,th.l{text-align:left}
.card h2:first-child{margin-top:0}td[class^=st-],td:last-child{white-space:nowrap}
.st-ok{color:#1f8a4c}.st-warn{color:#a86400}.st-fail{color:#c0392b}
"""


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def usd(x) -> str:
    if x is None:
        return "–"
    return f"${x:,.2f}" if x >= 1 else f"${x:,.3f}"


def ms(x) -> str:
    return "–" if x is None else f"{x / 1000:.1f} s"


def pct(x) -> str:
    return "–" if x is None else f"{x:.0%}"


def tile(value: str, label: str) -> str:
    return f'<div class="tile"><b>{esc(value)}</b><span>{esc(label)}</span></div>'


def cost_chart(daily: list[dict]) -> str:
    """Daily spend as bars, one hue; hover a bar for its day and amount."""
    w, h, pad_l, pad_b, pad_t = 720, 180, 44, 22, 8
    top = max((d["cost"] for d in daily), default=0) or 0.01
    plot_w, plot_h = w - pad_l, h - pad_b - pad_t
    step = plot_w / max(len(daily), 1)
    bar_w = max(step - 2, 1)  # 2px gap between bars
    parts = [
        f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="Daily model spend over the last {len(daily)} days">'
    ]
    for frac in (0, 0.5, 1):
        y = pad_t + plot_h * (1 - frac)
        parts.append(f'<line x1="{pad_l}" x2="{w}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(
            f'<text x="{pad_l - 6}" y="{y + 4:.1f}" text-anchor="end">{esc(usd(top * frac))}</text>'
        )
    for i, d in enumerate(daily):
        bh = plot_h * d["cost"] / top
        x, y = pad_l + i * step + 1, pad_t + plot_h - bh
        parts.append(
            f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
            f'height="{max(bh, 0):.1f}" rx="{min(2, bar_w / 2):.1f}"><title>'
            f"{d['day']:%a %d %b}: {esc(usd(d['cost']))}</title></rect>"
        )
        if i % 7 == 0:
            parts.append(f'<text x="{x:.1f}" y="{h - 6}">{d["day"]:%d %b}</text>')
    parts.append("</svg>")
    return "".join(parts)


def render_body(data: dict) -> str:
    t, f = data["turns"], data["feedback"]
    rated = (f["up"] or 0) + (f["down"] or 0)
    latest_eval = next((e for e in data["evals"] if not e["subset"]), None)
    out = [
        "<h1>AI Ops</h1>",
        f'<p class="meta">Last {data["days"]} days, updated '
        f"{data['generated_at']:%a %d %b %Y, %H:%M} UTC. Totals only: no questions or answers "
        "are published.</p>",
        '<div class="tiles">',
        tile(usd(data["total_cost"]), f"model spend, {data['days']} days"),
        tile(f"{t['turns']:,}", "chat answers"),
        tile(ms(t["p50"]), "answer time, median"),
        tile(ms(t["p95"]), "answer time, slowest 5%"),
        tile(pct(f["up"] / rated) if rated else "–", f"thumbs up ({rated} rated)"),
        tile(
            pct(latest_eval["pass_rate"]) if latest_eval else "–", "eval pass rate, last full run"
        ),
        tile(str(f["promoted"] or 0), "thumbs-down answers made eval cases"),
        "</div>",
        '<section class="card"><h2>Daily spend</h2>',
        cost_chart(data["daily_cost"]),
        "</section>",
    ]
    rows = "".join(
        f'<tr><td class="l">{esc(a["area"])}</td><td>{a["calls"]:,}</td>'
        f"<td>{a['prompt_tokens'] + a['completion_tokens']:,}</td>"
        f"<td>{esc(usd(a['cost']))}</td></tr>"
        for a in data["by_area"]
    )
    out.append(
        '<section class="card"><h2>Where the spend goes</h2><div class="wrap"><table>'
        '<tr><th class="l">Area</th><th>Model calls</th><th>Tokens</th><th>Cost</th></tr>'
        f"{rows or '<tr><td colspan=4>No model calls in this period.</td></tr>'}"
        "</table></div></section>"
    )
    rows = "".join(
        f'<tr><td class="l">{e["run_at"]:%d %b %H:%M}</td><td class="l">{esc(e["dataset"])}'
        f"{' · ' + esc(e['subset']) if e['subset'] else ''}</td>"
        f"<td>{esc(e['prompt_version'])}</td>"
        f"<td>{e['cases']}</td><td>{pct(e['pass_rate'])}</td><td>{esc(usd(e['cost_usd']))}</td>"
        f"<td>{ms(e['latency_p50_ms'])}</td>"
        f"<td>{'✓ met' if e['passed_thresholds'] else '✕ below'}</td></tr>"
        for e in data["evals"]
    )
    out.append(
        '<section class="card"><h2>Eval runs</h2><div class="wrap"><table>'
        '<tr><th class="l">Run (UTC)</th><th class="l">Dataset</th><th>Prompt</th>'
        "<th>Cases</th><th>Passed</th><th>Cost</th><th>Median time</th><th>Thresholds</th></tr>"
        f"{rows or '<tr><td colspan=8>No eval runs recorded yet.</td></tr>'}"
        "</table></div></section>"
    )
    rows = "".join(
        f'<tr><td class="l">{esc(c["name"])}</td><td class="st-{esc(c["status"])}">'
        f'{STATUS_MARK.get(c["status"], esc(c["status"]))}</td><td class="l">{esc(c["detail"])}'
        f"</td><td>{c['checked_at']:%d %b %H:%M}</td></tr>"
        for c in data["freshness"]
    )
    out.append(
        '<section class="card"><h2>Data freshness</h2><div class="wrap"><table>'
        '<tr><th class="l">Check</th><th>Status</th><th class="l">Detail</th>'
        "<th>Checked (UTC)</th></tr>"
        f"{rows or '<tr><td colspan=4>No checks stored yet.</td></tr>'}"
        "</table></div></section>"
    )
    return "".join(out)
