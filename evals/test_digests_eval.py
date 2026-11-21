"""The digest eval checks on a hand-made digest; no model, no database."""

from evals import digests as ev


def digest(**over):
    d = {
        "kind": "matchweek_recap",
        "headline": "Arsenal stay top",
        "intro": {"text": "Arsenal won 2-1.", "sources": ["m1"], "cites": [1]},
        "sections": [
            {"title": f"S{i}", "bullets": [{"text": "x", "sources": ["t1"], "cites": [2]}]}
            for i in range(3)
        ]
        + [
            {
                "title": "All results",
                "generated_by": "code",
                "bullets": [{"text": "Arsenal 2-1 Chelsea", "sources": ["m1"], "cites": [1]}],
            }
        ],
        "checks": {"dropped": []},
    }
    return d | over


INDEX = {"m1": {"score": "2-1"}, "t1": {}}


def test_checks_pass_on_a_good_digest():
    d = digest()
    assert ev.check_citations(d).passed and ev.check_scores(d, INDEX).passed
    assert ev.check_coverage(d, {"results": [{"source_id": "m1"}]}).passed
    assert ev.check_format(d).passed and ev.check_kept(d).score == 1
    assert ev.check_mentions(d, {"must_mention": ["arsenal"]}).passed
    assert ev.check_mentions(d, {}).passed is None


def test_checks_catch_problems():
    d = digest(
        intro={"text": "Arsenal won 3-1.", "sources": ["m1"], "cites": []},
        headline="x" * 95,
        checks={"dropped": [{}] * 3},
    )
    assert not ev.check_citations(d).passed
    assert "3-1" in ev.check_scores(d, INDEX).detail
    assert not ev.check_coverage(d, {"results": [{"source_id": "m1"}, {"source_id": "m2"}]}).passed
    assert "headline 95 chars" in ev.check_format(d).detail
    assert not ev.check_kept(d).passed
    assert (
        ev.check_mentions(d, {"must_mention": ["Pochettino"]}).detail == "missing: ['Pochettino']"
    )
