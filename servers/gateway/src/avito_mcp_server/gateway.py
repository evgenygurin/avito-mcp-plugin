"""Композиция gateway (Фаза 2): scraper-движок + монтирование скелетов.

Gateway — «входная дверь» avito-mcp (архитектура по образцу dj-music,
docs/ARCHITECTURE.md). Движок парсинга (search/get_listing/check_proxy_health)
перенесён в scraper и проксируется сюда импортом — те же ``register(mcp)``
функции дают те же имена и общий ``Context`` (без IPC-оверхеда). Мониторинг,
экспорт, уведомления остаются в gateway; скелеты db/notify монтируются как
прокси с неймспейсами (их бизнес-логика — Фазы 3–4).
"""

from __future__ import annotations

import typing as t

from fastmcp import FastMCP
from fastmcp.server import create_proxy

from avito_mcp_db.server import mcp as db_mcp
from avito_mcp_notify.server import mcp as notify_mcp
from avito_mcp_scraper.logging_setup import setup_logging as setup_scraper_logging
from avito_mcp_shared.roles import ROLE_NAMESPACES, ServerRole

from .server import register_all

# (роль, инстанс скелета) для композиции — бизнес-логика этих серверов в
# Фазах 3–4; пока они отдают только status.
_COMPONENTS: t.Final[tuple[tuple[ServerRole, FastMCP], ...]] = (
    (ServerRole.DB, db_mcp),
    (ServerRole.NOTIFY, notify_mcp),
)


def build_gateway() -> FastMCP:
    """Собирает gateway: 7 тулз (3 из scraper) + проксированные db/notify."""
    gw = FastMCP("avito-mcp-gateway")

    # 7 тулз: движок (scraper) + gateway-тулзы + skills.
    register_all(gw)

    # Композиция скелетов db/notify: mount поверх create_proxy.
    for role, target_mcp in _COMPONENTS:
        gw.mount(create_proxy(target_mcp), namespace=ROLE_NAMESPACES[role])

    return gw


def main() -> None:
    """Точка входа gateway: сборка и запуск по stdio."""
    setup_scraper_logging(loggers=["avito_mcp_server", "avito_mcp_scraper"])
    build_gateway().run()


if __name__ == "__main__":
    main()
