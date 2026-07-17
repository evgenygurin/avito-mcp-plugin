#!/usr/bin/env python3
"""Проверка синхронности версий во всех манифестах плагина.

Запуск: `python3 scripts/check_versions.py` (или в pre-commit).
Exit 0 — все версии совпадают; exit 1 — рассинхрон.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _dig(data: object, *keys: object) -> object:
    for key in keys:
        data = data[key]  # type: ignore[index]
    return data


def _json(path: str, *keys: object) -> str:
    return str(_dig(json.loads((ROOT / path).read_text(encoding="utf-8")), *keys))


def _toml(path: str, *keys: object) -> str:
    return str(_dig(tomllib.loads((ROOT / path).read_text(encoding="utf-8")), *keys))


def main() -> int:
    sources = {
        ".claude-plugin/plugin.json": _json(".claude-plugin/plugin.json", "version"),
        ".claude-plugin/marketplace.json": _json(
            ".claude-plugin/marketplace.json", "plugins", 0, "version"
        ),
        "server/pyproject.toml": _toml("server/pyproject.toml", "project", "version"),
        "gemini-extension.json": _json("gemini-extension.json", "version"),
        ".cursor-plugin/plugin.json": _json(".cursor-plugin/plugin.json", "version"),
    }
    width = max(len(v) for v in sources.values())
    for path, version in sources.items():
        print(f"{version:<{width}}  {path}")

    versions = set(sources.values())
    if len(versions) == 1:
        print(f"\nOK: все версии синхронны ({versions.pop()})")
        return 0
    print(f"\nFAIL: рассинхрон версий: {sorted(versions)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
