"""FastMCP-сервер avito-mcp-server.

СТАТУС: заготовка (skeleton). Содержит рабочий инстанс FastMCP без тулз —
доменные тулзы парсинга (search_listings, get_listing, …) добавляются в пакет
`tools/` по мере реализации — см. docs/mcp-server.md и docs/avito-scraping.md.
"""

from __future__ import annotations

from fastmcp import FastMCP

from .skills_provider import register_skills

mcp = FastMCP("avito-mcp-server")

# Раздача skills/ по MCP (skill://<name>/…) — любому MCP-клиенту.
# graceful: если каталог skills/ не найден, сервер работает без раздачи.
register_skills(mcp)

# TODO: зарегистрировать парсинг-тулзы (listings) после реализации слоя обхода
# антибота — см. skills/scraping-avito и docs/avito-scraping.md.


def main() -> None:
    """Точка входа: запуск по stdio (дефолтный транспорт)."""
    mcp.run()


if __name__ == "__main__":
    main()
