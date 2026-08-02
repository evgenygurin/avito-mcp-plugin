"""Роли серверов avito-mcp.

Одна константа-источник правды: имя роли и неймспейс, под которым gateway
монтирует компонент (``mount(..., namespace=…)``). Фаза 1 — только скелетные
роли scraper/db/notify; gateway — «входная дверь» и держит движок.
"""

from __future__ import annotations

import enum
import typing as t

__all__ = ["ROLE_NAMESPACES", "ServerRole"]


class ServerRole(enum.StrEnum):
    """Роли серверов avito-mcp."""

    GATEWAY = "gateway"
    SCRAPER = "scraper"
    DB = "db"
    NOTIFY = "notify"


# Неймспейсы, под которыми gateway монтирует каждый скелет (видимость тулз
# вида ``scraper_status``, ``db_status``, ``notify_status``).
ROLE_NAMESPACES: t.Final[dict[ServerRole, str]] = {
    ServerRole.SCRAPER: "scraper",
    ServerRole.DB: "db",
    ServerRole.NOTIFY: "notify",
}
