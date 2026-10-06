"""Loads config.toml and engine/.env. Every number the rules use lives in config.toml."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

ENGINE_DIR = Path(__file__).resolve().parent.parent


def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or ENGINE_DIR / "config.toml"
    with path.open("rb") as f:
        config = tomllib.load(f)
    config["paths"] = {k: (ENGINE_DIR / v).resolve() for k, v in config["paths"].items()}
    return config


def load_env(path: Path | None = None) -> None:
    """Reads KEY=value lines from engine/.env into os.environ, without overriding
    variables that are already set."""
    path = path or ENGINE_DIR / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def platform_url(config: dict[str, Any]) -> str:
    """The platform the engine talks to: PLATFORM_URL from engine/.env when set (a
    deployed platform, for example on Vercel), else base_url in config.toml (local).
    Call after load_env(). The result is written back into config so run.json records it."""
    url = os.environ.get("PLATFORM_URL", "").strip() or config["platform"]["base_url"]
    config["platform"]["base_url"] = url.rstrip("/")
    return config["platform"]["base_url"]


def require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"{name} is not set. Put it in engine/.env (see .env.example).")
    return value
