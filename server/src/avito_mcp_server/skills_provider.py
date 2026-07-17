"""Раздача каталога skills/ по MCP через FastMCP SkillsProvider.

Позволяет любому MCP-клиенту получить skills плагина как ресурсы
(`skill://<name>/SKILL.md`). Путь к skills/ разрешается gracefully — при
установке из PyPI (`uvx`) каталог берётся из ${CLAUDE_PLUGIN_ROOT}.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.providers.skills import SkillsProvider


def resolve_skills_dir() -> Path | None:
    """Найти каталог skills/ плагина.

    Приоритет:
    1. ``AVITO_SKILLS_DIR`` — явный override (если не каталог → None);
    2. ``${CLAUDE_PLUGIN_ROOT}/skills`` — при установке плагина;
    3. ``skills/`` относительно репозитория (режим разработки).
    """
    override = os.environ.get("AVITO_SKILLS_DIR")
    if override is not None:
        p = Path(override)
        return p if p.is_dir() else None

    candidates: list[Path] = []
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        candidates.append(Path(root) / "skills")
    candidates.append(Path(__file__).resolve().parents[3] / "skills")

    for c in candidates:
        if c.is_dir():
            return c
    return None


def register_skills(mcp: FastMCP) -> bool:
    """Зарегистрировать раздачу skills по MCP.

    Возвращает False, если каталог skills/ не найден (сервер продолжает
    работать без раздачи skills).
    """
    skills_dir = resolve_skills_dir()
    if skills_dir is None:
        return False
    mcp.add_provider(SkillsProvider(roots=skills_dir))
    return True
