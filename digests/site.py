"""Static GitHub Pages site for the weekly summaries, rendered from the digests table.

The site lives on the `gh-pages` branch, not on main: `publish` writes into a git worktree of
that branch and pushes it, so it never touches whatever branch the repo has checked out. Pages
serves the branch as it is (Settings > Pages > Deploy from a branch > gh-pages).
"""

import html
import json
import subprocess
from datetime import date, datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from backend.observability import dashboard

BRANCH = "gh-pages"
KIND_LABEL = {"matchweek_recap": "Matchweek recap", "news_highlights": "News highlights"}
SHOWCASE_DIR = Path("docs/showcase")  # conversations.json + screenshots, recorded locally

CSS = """
:root{--bg:#faf9fc;--fg:#1f1530;--muted:#6b6280;--card:#fff;--line:#e6e1ee;--accent:#4b1f7a;
--chip:#e3f3ea;--chip-fg:#1f5c3a}
@media (prefers-color-scheme:dark){:root{--bg:#18121f;--fg:#efeaf5;--muted:#a79fb5;
--card:#211a2b;--line:#352c42;--accent:#7fd8a8;--chip:#24392e;--chip-fg:#bfe9d1}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.6 Inter,system-ui,sans-serif}main{max-width:760px;margin:0 auto;padding:24px 16px 64px}
a{color:var(--accent)}header.site{border-bottom:1px solid var(--line);background:var(--card)}
header.site div{max-width:760px;margin:0 auto;padding:12px 16px;display:flex;gap:16px;
align-items:center;flex-wrap:wrap}header.site strong{font-size:15px}
header.site nav{display:flex;gap:12px;font-size:14px}
h1{font-size:28px;line-height:1.25;margin:8px 0}h2{font-size:19px;margin:28px 0 8px}
.meta{color:var(--muted);font-size:14px}.card{background:var(--card);border:1px solid var(--line);
border-radius:14px;padding:16px;margin:16px 0}ul{padding-left:20px}li{margin:6px 0}
sup a{display:inline-block;min-width:16px;padding:0 4px;border-radius:4px;background:var(--chip);
color:var(--chip-fg);font-size:11px;font-weight:600;text-decoration:none;text-align:center}
ol.sources{font-size:14px;color:var(--muted)}table{width:100%;border-collapse:collapse;font-size:14px;
font-variant-numeric:tabular-nums}
th,td{padding:4px 6px;border-top:1px solid var(--line);text-align:center}
th:nth-child(2),td:nth-child(2){text-align:left}.up{color:#1f8a4c}.down{color:#c0392b}
.wrap{overflow-x:auto}img{max-width:100%;border-radius:10px;border:1px solid var(--line)}
.q{font-weight:600}.archive li{display:flex;justify-content:space-between;gap:12px}
"""


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def page(title: str, body: str, root: str = "") -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><link rel="stylesheet" href="{root}style.css"></head>
<body><header class="site"><div><strong>Premier League Chat</strong><nav>
<a href="{root}index.html">This week</a><a href="{root}archive.html">Archive</a>
<a href="{root}showcase.html">Showcase</a><a href="{root}ops.html">AI Ops</a></nav></div></header>
<main>{body}</main></body></html>
"""


def cited(item: dict) -> str:
    sups = "".join(f'<sup><a href="#s{n}">{n}</a></sup>' for n in item.get("cites", []))
    return f"{esc(item['text'])}{sups}"


def table_html(table: dict) -> str:
    rows = "".join(
        f"<tr><td>{r['position']}</td><td>{esc(r['club'])}</td><td>{r['played']}</td>"
        f"<td>{r['goal_difference']:+d}</td><td><b>{r['points']}</b></td><td>{move(r)}</td></tr>"
        for r in table["rows"]
    )
    return (
        f'<h2>Table after matchweek {table["after_matchweek"]}</h2><div class="wrap"><table>'
        "<tr><th>#</th><th>Club</th><th>P</th><th>GD</th><th>Pts</th><th></th></tr>"
        f"{rows}</table></div>"
    )


def move(r: dict) -> str:
    g = r.get("places_gained", 0)
    if g > 0:
        return f'<span class="up" title="up {g}">▲{g}</span>'
    if g < 0:
        return f'<span class="down" title="down {-g}">▼{-g}</span>'
    return ""


def digest_html(d: dict) -> str:
    when = d["created_at"].strftime("%A %d %B %Y") if isinstance(d["created_at"], datetime) else ""
    parts = [
        f'<p class="meta">{KIND_LABEL[d["kind"]]} · published {esc(when)}</p>',
        f"<h1>{esc(d['headline'])}</h1>",
    ]
    content = d["content"]
    if content.get("intro"):
        parts.append(f"<p>{cited(content['intro'])}</p>")
    for s in content["sections"]:
        items = "".join(f"<li>{cited(b)}</li>" for b in s["bullets"])
        parts.append(f'<section class="card"><h2>{esc(s["title"])}</h2><ul>{items}</ul></section>')
    if d["kind"] == "matchweek_recap" and d.get("facts", {}).get("table"):
        parts.append(table_html(d["facts"]["table"]))
    srcs = "".join(
        f'<li id="s{s["n"]}"><a href="{esc(s["url"])}">{esc(s["title"])}</a>'
        + (f" · {esc(s['date'])}" if s.get("date") else "")
        + "</li>"
        for s in d["sources"]
    )
    parts.append(f'<h2>Sources</h2><ol class="sources">{srcs}</ol>')
    return "".join(parts)


def latest_digests(conn: psycopg.Connection) -> list[dict]:
    """The newest version of each (kind, period), newest period first."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT DISTINCT ON (kind, period_key) id, kind, period_key, period_end, created_at, "
            "headline, content, sources, facts FROM digests "
            "ORDER BY kind, period_key, created_at DESC"
        ).fetchall()


def slug(d: dict) -> str:
    return f"digests/{d['kind'].replace('_', '-')}-{d['period_key']}.html"


def showcase_html(showcase_dir: Path) -> str:
    convo_file = showcase_dir / "conversations.json"
    convos = json.loads(convo_file.read_text(encoding="utf-8")) if convo_file.exists() else []
    shots = sorted(showcase_dir.glob("*.png"))
    parts = [
        "<h1>Showcase</h1>",
        '<p class="meta">The chatbot runs locally (it needs a database and an Azure OpenAI '
        "deployment), so this page shows screenshots and recorded conversations.</p>",
    ]
    for p in shots:
        parts.append(
            f'<p><img src="showcase/{esc(p.name)}" alt="{esc(p.stem.replace("-", " "))}"></p>'
        )
    for c in convos:
        srcs = "".join(
            f'<li><a href="{esc(s["url"])}">{esc(s["title"])}</a></li>'
            for s in c.get("sources", [])
        )
        parts.append(
            f'<section class="card"><p class="q">{esc(c["question"])}</p>'
            f"<p>{esc(c['answer']).replace(chr(10), '<br>')}</p>"
            f'<ol class="sources">{srcs}</ol></section>'
        )
    if not shots and not convos:
        parts.append("<p>Screenshots and example conversations will appear here.</p>")
    return "".join(parts)


def render(
    conn: psycopg.Connection, showcase_dir: Path = SHOWCASE_DIR, now: datetime | None = None
) -> dict[str, bytes]:
    """Every file of the site, as {path: content}. Deterministic for the same data and `now`."""
    css = CSS.strip() + dashboard.CSS
    files: dict[str, bytes] = {"style.css": css.encode(), ".nojekyll": b""}
    digests = latest_digests(conn)
    for d in digests:
        files[slug(d)] = page(d["headline"], digest_html(d), "../").encode()
    newest = {}
    for d in sorted(digests, key=lambda d: d["created_at"], reverse=True):
        newest.setdefault(d["kind"], d)
    body = [
        "<h1>This week in the Premier League</h1>",
        '<p class="meta">Written every Tuesday (matchweek recap) and Friday (news highlights) '
        "from the official data and premierleague.com articles. Every line cites its source."
        "</p>",
    ]
    for kind in ("matchweek_recap", "news_highlights"):
        if d := newest.get(kind):
            body.append(
                f'<section class="card"><p class="meta">{KIND_LABEL[kind]}</p>'
                f'<h2><a href="{slug(d)}">{esc(d["headline"])}</a></h2>'
                f"<p>{esc((d['content'].get('intro') or {}).get('text', ''))}</p></section>"
            )
    if not newest:
        body.append("<p>The first digest will appear after the next scheduled run.</p>")
    files["index.html"] = page("This week in the Premier League", "".join(body)).encode()
    items = "".join(
        f'<li><a href="{slug(d)}">{esc(d["headline"])}</a>'
        f'<span class="meta">{KIND_LABEL[d["kind"]]}</span></li>'
        for d in sorted(digests, key=lambda d: d["created_at"], reverse=True)
    )
    files["archive.html"] = page(
        "Archive", f'<h1>Archive</h1><ul class="archive">{items}</ul>'
    ).encode()
    files["showcase.html"] = page("Showcase", showcase_html(showcase_dir)).encode()
    files["ops.html"] = page("AI Ops", dashboard.render_body(dashboard.gather(conn, now))).encode()
    for p in sorted(showcase_dir.glob("*.png")):
        files[f"showcase/{p.name}"] = p.read_bytes()
    return files


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def publish(files: dict[str, bytes], repo: Path, push: bool = False) -> dict:
    """Write the site into a worktree of the gh-pages branch, commit, and optionally push."""
    tree = repo / ".site"
    on_remote = _remote_has(repo)
    if not (tree / ".git").exists():
        if on_remote:
            git("fetch", "origin", BRANCH, cwd=repo)
            git("worktree", "add", "-f", "-B", BRANCH, str(tree), f"origin/{BRANCH}", cwd=repo)
        else:  # first publish: an orphan branch that shares no history with main
            git("worktree", "add", "--detach", str(tree), cwd=repo)
            git("checkout", "--orphan", BRANCH, cwd=tree)
            git("rm", "-rf", "--quiet", ".", cwd=tree)
    elif on_remote:
        git("pull", "--ff-only", "origin", BRANCH, cwd=tree)
    for path, content in files.items():
        target = tree / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    git("add", "-A", cwd=tree)
    if not git("status", "--porcelain", cwd=tree):
        return {"changed": False, "pushed": False}
    git("commit", "-m", f"Publish weekly summaries ({date.today().isoformat()})", cwd=tree)
    if push:
        git("push", "-u", "origin", BRANCH, cwd=tree)
    return {"changed": True, "pushed": push}


def _remote_has(repo: Path) -> bool:
    out = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", BRANCH], cwd=repo, capture_output=True, text=True
    )
    return bool(out.stdout.strip())
