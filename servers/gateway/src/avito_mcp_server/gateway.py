"""Композиция gateway (Фазы 2–4): scraper-движок + монтирование серверов.

Gateway — «входная дверь» avito-mcp (архитектура по образцу dj-music,
docs/ARCHITECTURE.md). Движок парсинга (search/get_listing/check_proxy_health),
БД/экспорт и уведомления проксируются сюда импортом — те же ``register(mcp)``
функции дают те же имена и общий ``Context`` (без IPC-оверхеда); скелеты
db/notify дополнительно монтируются как прокси с неймспейсами.
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

# (роль, инстанс) для композиции — поверх импортированных тулз дополнительные
# прокси-пространства (``db_status``, ``notify_status``, ``notify_send_*``).
_COMPONENTS: t.Final[tuple[tuple[ServerRole, FastMCP], ...]] = (
    (ServerRole.DB, db_mcp),
    (ServerRole.NOTIFY, notify_mcp),
)


def build_gateway() -> FastMCP:
    """Собирает gateway: тулзы импортом (scraper/db/notify) + прокси db/notify."""
    gw = FastMCP("avito-mcp-gateway")

    # Тулзы: движок (scraper) + gateway-мониторинг + делегированные db/notify.
    register_all(gw)

    # Композиция db/notify: mount поверх create_proxy.
    for role, target_mcp in _COMPONENTS:
        gw.mount(create_proxy(target_mcp), namespace=ROLE_NAMESPACES[role])

    return gw


def main() -> None:
    """Точка входа gateway: сборка и запуск по stdio."""
    setup_scraper_logging(loggers=["avito_mcp_server", "avito_mcp_scraper"])
    build_gateway().run()


if __name__ == "__main__":
    main()
