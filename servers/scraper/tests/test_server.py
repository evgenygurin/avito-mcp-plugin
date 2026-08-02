"""Смоук-тест scraper-сервера (Фаза 2): движок + 3 парсинг-тулзы.

Регистрирует search_listings / get_listing / check_proxy_health — без
мониторинга/экспорта/уведомлений (это gateway-композиция, Фазы 3–4).
"""

from fastmcp import Client

from avito_mcp_scraper.server import mcp

ENGINE_TOOLS = {"search_listings", "get_listing", "check_proxy_health"}


async def test_server_registers_engine_tools() -> None:
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
        assert ENGINE_TOOLS <= names, f"не хватает тулз движка: {ENGINE_TOOLS - names}"


async def test_server_has_no_gateway_only_tools() -> None:
    # Scraper stateless: никаких тулз, требующих хранилища/экспорта/уведомлений.
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
        forbidden = {
            "scan_new_listings",
            "get_price_history",
            "export_listings",
            "send_notification",
        }
        assert not (forbidden & names), f"в scraper не должны быть: {forbidden & names}"
