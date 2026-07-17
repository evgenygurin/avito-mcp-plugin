"""FastMCP-сервер avito-mcp-server.

СТАТУС: заготовка (skeleton). Содержит рабочий инстанс FastMCP и одну
диагностическую тулзу `ping` для проверки связи. Доменные тулзы (search_listings,
get_listing, official_api_call, …) добавляются в пакет `tools/` по мере
реализации — см. docs/mcp-server.md и docs/avito-scraping.md.
"""

from __future__ import annotations

from fastmcp import FastMCP
from pydantic import BaseModel

mcp = FastMCP("avito-mcp-server")


class Pong(BaseModel):
    """Ответ диагностической тулзы."""

    message: str
    length: int


@mcp.tool
async def ping(message: str = "ping") -> Pong:
    """Проверка связи с сервером. Возвращает сообщение и его длину.

    Use for connectivity checks — доменной логики не несёт.
    """
    return Pong(message=message, length=len(message))


# TODO: зарегистрировать доменные тулзы, например:
#   from .tools import listings, official_api
#   listings.register(mcp)
#   official_api.register(mcp)


def main() -> None:
    """Точка входа: запуск по stdio (дефолтный транспорт)."""
    mcp.run()


if __name__ == "__main__":
    main()
