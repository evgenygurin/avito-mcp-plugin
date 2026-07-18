"""FastMCP-сервер avito-mcp-server.

Регистрирует парсинг-тулзы (`search_listings`, `check_proxy_health`) поверх движка
и раздачу `skills/` по MCP. Прочие тулзы (get_listing, scan_new_listings, …)
добавляются в пакет `tools/` по мере реализации — см. docs/mcp-server.md.
"""

from __future__ import annotations

from fastmcp import FastMCP

from .skills_provider import register_skills
from .tools import diagnostics, search

mcp = FastMCP("avito-mcp-server")

# Парсинг-тулзы поверх движка.
search.register(mcp)
diagnostics.register(mcp)

# Раздача skills/ по MCP (skill://<name>/…) — любому MCP-клиенту.
# graceful: если каталог skills/ не найден, сервер работает без раздачи.
register_skills(mcp)


def main() -> None:
    """Точка входа: запуск по stdio (дефолтный транспорт)."""
    mcp.run()


if __name__ == "__main__":
    main()
