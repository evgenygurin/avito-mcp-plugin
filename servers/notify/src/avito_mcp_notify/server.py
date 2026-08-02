"""FastMCP-инстанс notify-сервера (скелет Фазы 1).

Предоставляет минимальный инструмент ``status`` (роль и готовность).
Уведомления (фаза 4) добавляются без изменения контракта gateway.
"""

from __future__ import annotations

from fastmcp import FastMCP

from avito_mcp_shared.roles import ServerRole

mcp = FastMCP("avito-mcp-notify")


@mcp.tool
async def status() -> dict[str, str]:
    """Возвращает роль и готовность notify-сервера."""
    return {"role": ServerRole.NOTIFY.value, "status": "ok"}


def main() -> None:
    """Точка входа: запуск по stdio (дефолтный транспорт)."""
    mcp.run()


if __name__ == "__main__":
    main()
