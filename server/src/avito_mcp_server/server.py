"""FastMCP-сервер avito-mcp-server.

Регистрирует 7 MCP-тулз поверх движка парсинга и раздачу ``skills/`` по MCP.
См. docs/mcp-server.md.
"""

from __future__ import annotations

from fastmcp import FastMCP

from .skills_provider import register_skills
from .tools import diagnostics, exporting, listings, monitoring, notifications, search

mcp = FastMCP("avito-mcp-server")

# Парсинг-тулзы поверх движка.
search.register(mcp)
listings.register(mcp)
diagnostics.register(mcp)

# Мониторинг (состояние / история цены).
monitoring.register(mcp)

# Сайд-эффекты: экспорт и уведомления.
exporting.register(mcp)
notifications.register(mcp)

# Раздача skills/ по MCP (skill://<name>/…) — любому MCP-клиенту.
# graceful: если каталог skills/ не найден, сервер работает без раздачи.
register_skills(mcp)


def main() -> None:
    """Точка входа: запуск по stdio (дефолтный транспорт)."""
    mcp.run()


if __name__ == "__main__":
    main()
