"""Code evaluators. Each takes (case, transcript, ...) and returns a Check.

A transcript is a dict built by the runner from one chat turn:
  answer: str, question: str, calls: [{name, arguments: dict, error?}],
  tool_outputs: [str (JSON text the model saw)], retrieved: [search_news result dicts],
  cited: [structured sources the answer cites, see backend/llm/citations.py],
  dropped: [citation markers the backend dropped because no tool returned them]
"""

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal

from backend.tools.resolver import normalize, resolve_club


@dataclass
class Check:
    passed: bool | None  # None = not applicable / skipped
    score: float | None = None
    detail: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


# ---------- matching answer text against expected values

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]  # fmt: skip


def _number_in(text: str, n) -> bool:
    plain = text.replace(",", "")  # 60,704 -> 60704
    s = format(Decimal(str(n)).normalize(), "f")
    return re.search(rf"(?<![\d.]){re.escape(s)}(?![\d]|\.\d)", plain) is not None


def _date_in(norm_text: str, raw: str, d: date) -> bool:
    if d.isoformat() in raw:
        return True
    month = MONTHS[d.month - 1]
    mon = f"(?:{month}|{month[:3]})"
    day = rf"{d.day}(?:st|nd|rd|th)?"
    return bool(re.search(rf"\b{day}\s+(?:of\s+)?{mon}\b|\b{mon}\s+{day}\b", norm_text))


def value_found(answer: str, value) -> bool:
    """value: number, date, string ('a|b' = alternatives) or list of alternatives."""
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, (list, tuple)):
        options = [v for v in value if v not in (None, "")]
        return not options or any(value_found(answer, v) for v in options)
    norm = f" {normalize(answer)} "
    if isinstance(value, (int, float, Decimal)):
        return _number_in(answer, value)
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return _date_in(norm, answer, value)
    text = str(value)
    if "|" in text:
        return any(value_found(answer, part) for part in text.split("|"))
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return _number_in(answer, text)
    if re.fullmatch(r"\d+-\d+(-\d+)*", text):  # a formation such as 4-2-3-1
        return text in answer.replace("–", "-")
    return f" {normalize(text)} " in norm or normalize(text) in norm.replace(" ", "")


def _show(row) -> str:
    return ", ".join(str(v[0] if isinstance(v, list) else v) for v in row)


def exact_answer(case: dict, t: dict, expected_rows: list[tuple] | None) -> Check:
    golden = case.get("golden") or {}
    answer = t["answer"]
    if "facts" in golden:
        missing = [f for f in golden["facts"] if not value_found(answer, f)]
        n = len(golden["facts"])
        return Check(not missing, (n - len(missing)) / n,
                     f"missing facts: {missing}" if missing else "")  # fmt: skip
    if expected_rows is None:
        return Check(None, detail="no golden")
    rows = [r for r in expected_rows if any(v is not None for v in r)]
    if not rows:
        return Check(None, detail="golden query returned nothing")
    found = [all(value_found(answer, v) for v in r) for r in rows]
    share = sum(found) / len(found)
    mode = golden.get("match", "all")
    if mode == "any":
        ok = any(found)
    elif mode.startswith("fraction:"):
        ok = share >= float(mode.split(":")[1])
    else:
        ok = all(found)
    missing = [_show(r) for r, f in zip(rows, found, strict=True) if not f][:5]
    return Check(ok, share, f"not found: {missing}" if missing else "")


# ---------- tool selection


def tool_selection(case: dict, t: dict, conn=None) -> Check:
    expected = case.get("expected_tools") or []
    called = [c["name"] for c in t["calls"]]
    if not expected:
        return Check(not called, 1.0 if not called else 0.0,
                     f"expected no tools, called {called}" if called else "")  # fmt: skip
    groups = [g if isinstance(g, list) else [g] for g in expected]
    hit = [any(n in called for n in g) for g in groups]
    recall = sum(hit) / len(groups)
    allowed = {n for g in groups for n in g} | set(case.get("allowed_tools", []))
    precision = sum(n in allowed for n in called) / len(called) if called else 0.0
    problems = []
    if recall < 1:
        problems.append(f"missing {[g for g, h in zip(groups, hit, strict=True) if not h]}")
    if called and precision < 0.5:
        problems.append(f"mostly unexpected tools {called}")
    for ac in case.get("arg_checks", []):
        values = [c["arguments"][ac["arg"]] for c in t["calls"] if ac["arg"] in c["arguments"]]
        if not values:
            if not ac.get("optional"):
                problems.append(f"no call passed {ac['arg']}")
            continue
        if "equals" in ac and ac["equals"] not in values:
            problems.append(f"{ac['arg']}={values}, expected {ac['equals']}")
        if "club_id" in ac and conn is not None:
            ids = set()
            for v in values:
                r = resolve_club(conn, str(v))
                ids.add(r.match["id"] if r.match else None)
            if ac["club_id"] not in ids:
                problems.append(f"{ac['arg']}={values} does not resolve to club {ac['club_id']}")
    return Check(not problems, recall * (precision if called else 0), "; ".join(problems))


# ---------- numbers must come from tools

SEASON = re.compile(r"\b20\d\d[-/](?:20)?\d\d\b")
URL = re.compile(r"https?://\S+")
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
CITATION_MARKER = re.compile(r"\[\d+\]")
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")


def _norm_num(n: str) -> str:
    return format(Decimal(n).normalize(), "f")


def numbers(text: str) -> set[str]:
    text = CITATION_MARKER.sub(" ", text)
    text = LIST_MARKER.sub(" ", SEASON.sub(" ", URL.sub(" ", text)))
    return {_norm_num(n) for n in NUMBER.findall(text.replace(",", ""))}


def no_ungrounded_numbers(case: dict, t: dict, context_numbers=frozenset()) -> Check:
    in_answer = numbers(t["answer"])
    if not in_answer:
        return Check(None, detail="no numbers in the answer")
    grounded = set(context_numbers) | numbers(t["question"])
    for out in t["tool_outputs"]:
        grounded |= {_norm_num(n) for n in re.findall(r"\d+(?:\.\d+)?", out)}
    loose = sorted(in_answer - grounded, key=float)
    return Check(not loose, 1 - len(loose) / len(in_answer),
                 f"numbers not in any tool result: {loose}" if loose else "")  # fmt: skip


# ---------- citations (structured: markers validated and resolved by the backend)


def citation(case: dict, t: dict) -> Check:
    """At least one valid citation, no invented markers, the expected article among them.
    News answers must cite an article; other answers may cite match, table or club sources."""
    cited, dropped = t.get("cited") or [], t.get("dropped") or []
    expected = (case.get("golden") or {}).get("articles") or []
    if not cited:
        return Check(
            False, 0.0, "nothing cited" + (f"; dropped markers {dropped}" if dropped else "")
        )
    problems = []
    if dropped:
        problems.append(f"markers not returned by any tool were dropped: {dropped}")
    articles = [s["id"] for s in cited if s["kind"] == "article"]
    hit = not expected or any(f"a{a}" in articles for a in expected)
    if expected and not hit:
        problems.append(f"none of the expected articles {expected} cited (cited {articles})")
    if case.get("category") == "news" and not articles:
        problems.append("news answer cites no article")
    precision = len(cited) / (len(cited) + len(dropped))
    return Check(not problems, precision * (1.0 if hit else 0.5), "; ".join(problems))


# ---------- retrieval (independent of the model: the question is searched directly)


def top_articles(hits: list[dict], n: int = 5) -> list[int]:
    seen: list[int] = []
    for h in hits:
        if h["article_id"] not in seen:
            seen.append(h["article_id"])
    return seen[:n]


def retrieval(case: dict, ranked_article_ids: list[int]) -> Check:
    expected = (case.get("golden") or {}).get("articles") or []
    if not expected:
        return Check(None, detail="no expected articles")
    rank = next((i for i, a in enumerate(ranked_article_ids, 1) if a in expected), None)
    return Check(rank is not None, 1 / rank if rank else 0.0,
                 f"rank {rank}" if rank else f"expected {expected} not in top 5")  # fmt: skip


# ---------- building a transcript from a chat turn


def transcript(question: str, answer: str, messages: list[dict]) -> dict:
    names = {}
    calls = []
    for m in messages:
        for tc in m.get("tool_calls") or []:
            names[tc["id"]] = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except ValueError:
                args = {}
            calls.append({"name": tc["function"]["name"], "arguments": args})
    outputs, retrieved = [], []  # retrieved: search_news results with source_id, title, text
    for m in messages:
        if m.get("role") != "tool":
            continue
        outputs.append(m["content"])
        if names.get(m["tool_call_id"]) == "search_news":
            try:
                retrieved += json.loads(m["content"]).get("results", [])
            except (ValueError, AttributeError):
                pass
    return {"question": question, "answer": answer, "calls": calls, "tool_outputs": outputs,
            "retrieved": retrieved}  # fmt: skip
