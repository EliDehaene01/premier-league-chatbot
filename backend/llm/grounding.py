"""Numbers in generated text, for checking them against the data they claim to come from.

Used by the eval suite (no ungrounded numbers in chat answers) and by the digest validator.
"""

import re
from decimal import Decimal

SEASON = re.compile(r"\b20\d\d[-/](?:20)?\d\d\b")
URL = re.compile(r"https?://\S+")
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
CITATION_MARKER = re.compile(r"\[(?:\d+|[a-z]\d[\w-]*)\]")
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")


def _norm_num(n: str) -> str:
    return format(Decimal(n).normalize(), "f")


def numbers(text: str) -> set[str]:
    """Numbers a reader would take as facts: not list markers, seasons, URLs or citations."""
    text = CITATION_MARKER.sub(" ", text)
    text = LIST_MARKER.sub(" ", SEASON.sub(" ", URL.sub(" ", text)))
    return {_norm_num(n) for n in NUMBER.findall(text.replace(",", ""))}


def numbers_in_data(data) -> set[str]:
    """Every number that appears anywhere in a JSON-like structure (keys excluded)."""
    found: set[str] = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list | tuple):
            for x in v:
                walk(x)
        elif isinstance(v, bool) or v is None:
            return
        elif isinstance(v, int | float):
            found.add(_norm_num(str(v)))
        else:
            found.update(_norm_num(n) for n in re.findall(r"\d+(?:\.\d+)?", str(v)))

    walk(data)
    return found
