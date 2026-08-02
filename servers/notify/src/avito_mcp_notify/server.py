"""FastMCP-инстанс notify-сервера (Фаза 4: уведомления).

Предоставляет ``status`` (роль/готовность) и тулзу ``send_notification``
(Telegram / VK, тот же контракт, что в gateway до Фазы 4).
"""

from __future__ import annotations

from fastmcp import FastMCP

from avito_mcp_shared.roles import ServerRole

from .tools.notifications import register as register_notifications

mcp = FastMCP("avito-mcp-notify")


@mcp.tool
async def status() -> dict[str, str]:
    """Возвращает роль и готовность notify-сервера."""
    return {"role": ServerRole.NOTIFY.value, "status": "ok"}


register_notifications(mcp)


def main() -> None:
    """Точка входа: запуск по stdio (дефолтный транспорт)."""
    mcp.run()


if __name__ == "__main__":
    main()
