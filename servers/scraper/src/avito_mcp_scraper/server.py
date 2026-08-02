"""FastMCP-инстанс scraper-сервера: движок парсинга (stateless).

Scraper — самостоятельный сервер без хранилища: http/cookies/proxies/parser/
filters + тулзы поиска/чтения/диагностики. Gateway композирует его и берёт
мониторинг/экспорт/уведомления (которые перенесёт в Фазы 3–4).
"""

from __future__ import annotations

from fastmcp import FastMCP

from .logging_setup import setup_logging
from .tools import diagnostics, listings, search

setup_logging()

mcp = FastMCP("avito-mcp-scraper")

# Парсинг-тулзы поверх движка (stateless — без записи в БД).
search.register(mcp)
listings.register(mcp)
diagnostics.register(mcp)


def main() -> None:
    """Точка входа: запуск по stdio (дефолтный транспорт)."""
    mcp.run()


if __name__ == "__main__":
    main()
