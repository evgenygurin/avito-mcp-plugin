"""FastMCP-инстанс scraper-сервера (скелет Фазы 1).

Предоставляет минимальный инструмент ``status`` (роль и готовность). Движок
парсинга (фаза 2) добавляется без изменения контракта gateway.
"""

from __future__ import annotations

from fastmcp import FastMCP

from avito_mcp_shared.roles import ServerRole

mcp = FastMCP("avito-mcp-scraper")


@mcp.tool
async def status() -> dict[str, str]:
    """Возвращает роль и готовность scraper-сервера."""
    return {"role": ServerRole.SCRAPER.value, "status": "ok"}


def main() -> None:
    """Точка входа: запуск по stdio (дефолтный транспорт)."""
    mcp.run()


if __name__ == "__main__":
    main()
