"""Тесты композиции gateway (Фаза 1): движок + mount/createProxy на скелеты.

Проверяют, что gateway видит 7 тулз движка и проксированные инструменты
скелетов scraper/db/notify под неймспейсами — критерий приёмки «Gateway
видит все 3 сервера (mount+proxy), тулзы проксируются».
"""

from fastmcp import Client

from avito_mcp_server.gateway import build_gateway

ENGINE_TOOLS = {
    "search_listings",
    "get_listing",
    "check_proxy_health",
    "scan_new_listings",
    "get_price_history",
    "export_listings",
    "send_notification",
}

PROXIED_TOOLS = {"scraper_status", "db_status", "notify_status"}


async def test_gateway_hosts_engine_and_proxied_components() -> None:
    async with Client(build_gateway()) as client:
        names = {t.name for t in await client.list_tools()}
        assert ENGINE_TOOLS <= names, f"не хватает тулз движка: {ENGINE_TOOLS - names}"
        assert PROXIED_TOOLS <= names, (
            f"нет проксированных скелетов: {PROXIED_TOOLS - names}"
        )


async def test_gateway_proxies_component_call() -> None:
    async with Client(build_gateway()) as client:
        result = await client.call_tool("scraper_status", {})
        assert result.data == {"role": "scraper", "status": "ok"}
