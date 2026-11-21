"""Versioned prompts: backend/prompts/system_<version>.md, filled with string.Template."""

from pathlib import Path
from string import Template

PROMPTS = Path(__file__).parent


def load_prompt(version: str, **values) -> str:
    return Template((PROMPTS / f"system_{version}.md").read_text(encoding="utf-8")).substitute(
        values
    )


def load_named(name: str, **values) -> str:
    """Any other versioned prompt, e.g. load_named("digest_recap_v1")."""
    return Template((PROMPTS / f"{name}.md").read_text(encoding="utf-8")).substitute(values)
