"""Add the self-hosted Langfuse settings to .env with fresh random values.

    python scripts/langfuse_env.py

Appends only the keys .env does not have yet and prints their names, never their values. The
login password for the Langfuse UI is in .env as LANGFUSE_INIT_USER_PASSWORD.
"""

import secrets
import sys
from pathlib import Path

ENV = Path(__file__).resolve().parents[1] / ".env"


def values() -> dict[str, str]:
    tok = secrets.token_urlsafe
    return {
        "LANGFUSE_HOST": "http://localhost:3000",
        "LANGFUSE_PUBLIC_KEY": f"pk-lf-{secrets.token_hex(16)}",
        "LANGFUSE_SECRET_KEY": f"sk-lf-{secrets.token_hex(16)}",
        "LANGFUSE_INIT_USER_EMAIL": "admin@localhost.test",
        "LANGFUSE_INIT_USER_PASSWORD": tok(18),
        "LANGFUSE_DB_PASSWORD": tok(24),
        "LANGFUSE_CLICKHOUSE_PASSWORD": tok(24),
        "LANGFUSE_MINIO_PASSWORD": tok(24),
        "LANGFUSE_REDIS_PASSWORD": tok(24),
        "LANGFUSE_NEXTAUTH_SECRET": tok(32),
        "LANGFUSE_SALT": tok(32),
        "LANGFUSE_ENCRYPTION_KEY": secrets.token_hex(32),  # 64 hex characters
    }


def main(env: Path = ENV) -> int:
    text = env.read_text(encoding="utf-8") if env.exists() else ""
    have = {line.split("=", 1)[0].strip() for line in text.splitlines() if "=" in line}
    new = {k: v for k, v in values().items() if k not in have}
    if new:
        block = "\n# Self-hosted Langfuse (scripts/langfuse_env.py)\n"
        block += "".join(f"{k}={v}\n" for k, v in new.items())
        env.write_text(text.rstrip("\n") + "\n" + block, encoding="utf-8")
    print("added:", ", ".join(new) or "nothing, all keys already set")
    return 0


if __name__ == "__main__":
    sys.exit(main())
