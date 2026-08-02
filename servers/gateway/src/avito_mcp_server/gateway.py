"""Композиция gateway: движок (7 тулз) + mount + create_proxy на скелеты.

Gateway — «входная дверь» avito-mcp (архитектура по образцу dj-music,
docs/ARCHITECTURE.md). Держит текущий движок с 7 тулзами и монтирует три
скелетных сервера (scraper/db/notify) как прокси с неймспейсами. Бизнес-логика
тулз не переносится — это фазы 2–4.
"""

from __future__ import annotations

import typing as t

from fastmcp import FastMCP
from fastmcp.server import create_proxy

from avito_mcp_db.server import mcp as db_mcp
from avito_mcp_notify.server import mcp as notify_mcp
from avito_mcp_scraper.server import mcp as scraper_mcp
from avito_mcp_shared.roles import ROLE_NAMESPACES, ServerRole

from .skills_provider import register_skills
from .tools import diagnostics, exporting, listings, monitoring, notifications, search

# (роль, инстанс скелета) для композиции.
_COMPONENTS: t.Final[tuple[tuple[ServerRole, FastMCP], ...]] = (
    (ServerRole.SCRAPER, scraper_mcp),
    (ServerRole.DB, db_mcp),
    (ServerRole.NOTIFY, notify_mcp),
)


def build_gateway() -> FastMCP:
    """Собирает gateway: 7 тулз движка + проксированные скелеты scraper/db/notify."""
    gw = FastMCP("avito-mcp-gateway")

    # Движок — те же группы тулз, что и в монолитном server.py.
    search.register(gw)
    listings.register(gw)
    diagnostics.register(gw)
    monitoring.register(gw)
    exporting.register(gw)
    notifications.register(gw)
    register_skills(gw)

    # Композиция компонентов: mount поверх create_proxy, неймспейсы из shared.
    for role, target_mcp in _COMPONENTS:
        gw.mount(create_proxy(target_mcp), namespace=ROLE_NAMESPACES[role])

    return gw


def main() -> None:
    """Точка входа gateway: сборка и запуск по stdio."""
    build_gateway().run()


if __name__ == "__main__":
    main()
