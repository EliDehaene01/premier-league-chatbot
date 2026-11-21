"""python -m digests recap|news|publish

    recap   [--matchweek N]           write the matchweek recap (default: latest complete one)
    news    [--week-ending DATE]      write the news highlights for the 7 days before DATE
            [--publish]               then render the site and push it (the scheduled runs)
    publish [--push | --out DIR]      render the GitHub Pages site from stored digests

recap and news print the digest; --dry-run skips storing it. Both exit 1 when no digest could
be written (no complete matchweek, Prompt Shields down, nothing survived validation).
"""

import argparse
import json
import sys
from datetime import UTC, datetime, time
from pathlib import Path

from backend.db import get_connection, init_db
from backend.llm.providers import AzureOpenAIProvider
from digests import site
from digests.config import load_weights
from digests.writer import DigestError, write_news, write_recap


def summary(d: dict) -> dict:
    return {
        "id": d.get("id"),
        "kind": d["kind"],
        "period": d["period_key"],
        "headline": d["headline"],
        "sections": [s["title"] for s in d["sections"]],
        "sources": len(d["sources"]),
        "dropped": len(d["checks"]["dropped"]),
        "cost_usd": d["cost_usd"],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m digests")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("recap")
    r.add_argument("--matchweek", type=int)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--publish", action="store_true", help="then publish and push the site")
    r.add_argument("--summary", type=Path)
    n = sub.add_parser("news")
    n.add_argument(
        "--week-ending",
        type=lambda s: datetime.combine(datetime.strptime(s, "%Y-%m-%d").date(), time(5), UTC),
    )
    n.add_argument("--dry-run", action="store_true")
    n.add_argument("--publish", action="store_true", help="then publish and push the site")
    n.add_argument("--summary", type=Path)
    p = sub.add_parser("publish")
    p.add_argument("--push", action="store_true", help="push the gh-pages branch to origin")
    p.add_argument("--out", type=Path, help="write the site to a folder instead (preview)")
    p.add_argument("--summary", type=Path, help="also write the result as JSON here")
    args = ap.parse_args(argv)

    conn = get_connection()
    init_db(conn)
    weights = load_weights()
    try:
        if args.cmd == "recap":
            d = write_recap(
                conn,
                AzureOpenAIProvider(conn, prompt_version="digest_recap_v1"),
                args.matchweek,
                cfg=weights["recap"],
                store=not args.dry_run,
            )
            out = summary(d)
        elif args.cmd == "news":
            d = write_news(
                conn,
                AzureOpenAIProvider(conn, prompt_version="digest_news_v1"),
                args.week_ending,
                cfg=weights["news"],
                store=not args.dry_run,
            )
            out = summary(d)
        if args.cmd in ("recap", "news") and args.publish and not args.dry_run:
            out["published"] = site.publish(site.render(conn), Path.cwd(), push=True)
        elif args.cmd == "publish":
            files = site.render(conn)
            if args.out:
                for path, content in files.items():
                    (args.out / path).parent.mkdir(parents=True, exist_ok=True)
                    (args.out / path).write_bytes(content)
                out = {"written": len(files), "to": str(args.out)}
            else:
                out = site.publish(files, Path.cwd(), push=args.push)
    except DigestError as e:
        out = {"error": str(e)}
    text = json.dumps(out, indent=2, default=str)
    print(text)
    if getattr(args, "summary", None):
        args.summary.write_text(text, encoding="utf-8")
    return 1 if "error" in out else 0


if __name__ == "__main__":
    sys.exit(main())
