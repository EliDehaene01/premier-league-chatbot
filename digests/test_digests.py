"""Pure digest logic: table maths, validation, clustering and ranking, rendering. No database."""

from datetime import UTC, datetime, timedelta

from digests import news, site
from digests.config import load_weights
from digests.recap import standings
from digests.writer import RECAP_SCHEMA, check_cited, results_section

NOW = datetime(2026, 11, 20, 5, tzinfo=UTC)


def m(h, a, hs, as_):
    return {"home_club_id": h, "away_club_id": a, "home_score": hs, "away_score": as_}


def test_standings_points_then_goal_difference_then_goals():
    clubs = {1: "Arsenal", 2: "Chelsea", 3: "Spurs", 4: "Everton"}
    table = standings([m(1, 2, 1, 0), m(3, 4, 3, 2), m(2, 4, 4, 0)], clubs)
    assert [(r["club"], r["points"], r["goal_difference"]) for r in table] == [
        ("Chelsea", 3, 3),
        ("Spurs", 3, 1),  # level with Arsenal on points and goal difference, more goals
        ("Arsenal", 3, 1),
        ("Everton", 0, -5),
    ]


INDEX = {
    "m1": {
        "source_id": "m1",
        "home": "Arsenal",
        "away": "Chelsea",
        "score": "2-1",
        "goals": [{"player": "Saka", "minute": "23"}],
    },
    "t10": {"rows": [{"position": 1, "club": "Arsenal", "points": 27}]},
}


def test_check_cited_keeps_grounded_bullets():
    drops = []
    out = check_cited(
        {"text": "Saka scored after 23 minutes as Arsenal won 2-1.", "sources": ["m1", "m99"]},
        INDEX,
        set(),
        drops,
        "b",
    )
    assert out == {"text": "Saka scored after 23 minutes as Arsenal won 2-1.", "sources": ["m1"]}
    assert drops == []


def test_check_cited_drops_unsourced_ungrounded_and_wrong_scores():
    drops = []
    assert (
        check_cited({"text": "Arsenal won.", "sources": ["m99"]}, INDEX, set(), drops, "a") is None
    )
    assert (
        check_cited(
            {"text": "Arsenal have 30 points.", "sources": ["t10"]}, INDEX, set(), drops, "b"
        )
        is None
    )
    assert check_cited({"text": "Arsenal won 1-2.", "sources": ["m1"]}, INDEX, set(), drops, "c")
    assert (
        check_cited({"text": "Arsenal won 2-0.", "sources": ["m1"]}, INDEX, {"0"}, drops, "d")
        is None
    )
    assert [d["where"] for d in drops] == ["a", "b", "d"]
    assert "30" in drops[1]["reason"] and "2-0" in drops[2]["reason"]


def test_results_section_is_written_by_code():
    facts = {
        "results": [
            {
                "source_id": "m1",
                "home": "Arsenal",
                "away": "Chelsea",
                "score": "2-1",
                "goals": [
                    {"player": "Saka", "minute": "23"},
                    {"player": "Gabriel", "minute": "60", "type": "OwnGoal"},
                    {"player": "Saka", "minute": "88", "type": "Penalty"},
                ],
            }
        ],
        "catch_up_results": [],
        "pending_fixtures": [{"source_id": "m2", "home": "Spurs", "away": "Everton"}],
    }
    s = results_section(facts)
    assert (
        s["bullets"][0]["text"] == "Arsenal 2-1 Chelsea: Saka 23', Gabriel 60' (og), Saka 88' (pen)"
    )
    assert s["bullets"][1] == {"text": "Spurs v Everton is still to be played", "sources": ["m2"]}


def test_recap_schema_is_strict():
    assert RECAP_SCHEMA["additionalProperties"] is False
    assert set(RECAP_SCHEMA["required"]) == {"headline", "intro", "sections"}


def art(i, vec, hours_ago):
    return {
        "content_id": i,
        "title": f"t{i}",
        "description": "",
        "embedding": vec,
        "published_at": NOW - timedelta(hours=hours_ago),
    }


def test_cluster_groups_similar_articles_newest_first():
    arts = [art(1, [1, 0], 1), art(2, [0.95, 0.05], 2), art(3, [0, 1], 3), art(4, None, 4)]
    stories = news.cluster(arts, 0.8)
    assert [[a["content_id"] for a in s] for s in stories] == [[1, 2], [3], [4]]


def test_rank_uses_config_weights_not_the_model():
    cfg = load_weights()["news"]
    stories = [[art(1, None, 1)], [art(2, None, 50), art(3, None, 60), art(4, None, 70)]]
    ranked = news.rank(stories, {0: "other", 1: "manager_change"}, NOW, cfg)
    assert [r["story"] for r in ranked] == [1, 0]
    assert news.rank(stories, {0: "made_up_type"}, NOW, cfg)[1]["type"] == "other"
    again = news.rank(stories, {0: "other", 1: "manager_change"}, NOW, cfg)
    assert [r["score"] for r in again] == [r["score"] for r in ranked]


def test_digest_page_escapes_and_links_citations():
    d = {
        "kind": "matchweek_recap",
        "created_at": NOW,
        "headline": "Arsenal <b>win</b>",
        "content": {
            "intro": {"text": "A & B", "cites": [1]},
            "sections": [{"title": "Top", "bullets": [{"text": "x", "cites": [1, 2]}]}],
        },
        "sources": [
            {
                "n": 1,
                "title": "Arsenal 2-1 Chelsea",
                "date": "2026-11-08",
                "url": "https://www.premierleague.com/en/match/1",
            }
        ],
        "facts": {
            "table": {
                "after_matchweek": 10,
                "rows": [
                    {
                        "position": 1,
                        "club": "Arsenal",
                        "played": 10,
                        "goal_difference": 10,
                        "points": 27,
                        "places_gained": 2,
                    }
                ],
            }
        },
    }
    out = site.digest_html(d)
    assert "Arsenal &lt;b&gt;win&lt;/b&gt;" in out and "A &amp; B" in out
    assert '<sup><a href="#s2">2</a></sup>' in out and 'id="s1"' in out
    assert "▲2" in out and "Table after matchweek 10" in out


def test_showcase_page_without_recordings(tmp_path):
    assert "will appear here" in site.showcase_html(tmp_path)
    (tmp_path / "conversations.json").write_text(
        '[{"question": "Who is top?", "answer": "Arsenal [1]", '
        '"sources": [{"title": "Table", "url": "https://x"}]}]'
    )
    assert "Who is top?" in site.showcase_html(tmp_path)


def test_publish_writes_an_orphan_gh_pages_branch_then_updates_it(tmp_path):
    import subprocess

    def git(*a, cwd):
        return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)

    remote, repo = tmp_path / "remote.git", tmp_path / "repo"
    git("init", "--bare", "-q", str(remote), cwd=tmp_path)
    git("init", "-q", "-b", "main", str(repo), cwd=tmp_path)
    for k, v in (("user.email", "t@example.com"), ("user.name", "t")):
        git("config", k, v, cwd=repo)
    (repo / "README.md").write_text("main branch")
    git("add", ".", cwd=repo)
    git("commit", "-qm", "init", cwd=repo)
    git("remote", "add", "origin", str(remote), cwd=repo)

    assert site.publish({"index.html": b"v1"}, repo, push=True) == {"changed": True, "pushed": True}
    assert git("show", "gh-pages:index.html", cwd=remote).stdout == "v1"
    assert "README.md" not in git("ls-tree", "--name-only", "gh-pages", cwd=remote).stdout
    assert git("branch", "--show-current", cwd=repo).stdout.strip() == "main"  # untouched
    assert site.publish({"index.html": b"v1"}, repo, push=True)["changed"] is False
    site.publish({"index.html": b"v2", "digests/a.html": b"a"}, repo, push=True)
    assert git("show", "gh-pages:index.html", cwd=remote).stdout == "v2"
