"""Тесты композиции gateway (Фаза 2): scraper-движок + mount на db/notify.

Gateway видит 7 тулз: 3 из scraper-движка (импорт, те же имена) + 4 gateway
(мониторинг/экспорт/уведомления), плюс проксированные скелеты db/notify под
неймспейсами. Scraper больше НЕ монтируется как прокси — его тулзы входят
в gateway импортом (общий контекст, без IPC-оверхеда).
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

PROXIED_TOOLS = {"db_status", "notify_status"}


async def test_gateway_hosts_engine_and_proxied_components() -> None:
    async with Client(build_gateway()) as client:
        names = {t.name for t in await client.list_tools()}
        assert ENGINE_TOOLS <= names, f"не хватает тулз движка: {ENGINE_TOOLS - names}"
        assert PROXIED_TOOLS <= names, (
            f"нет проксированных скелетов: {PROXIED_TOOLS - names}"
        )


async def test_gateway_proxies_component_call() -> None:
    async with Client(build_gateway()) as client:
        result = await client.call_tool("db_status", {})
        assert result.data == {"role": "db", "status": "ok"}


async def test_gateway_contract_keeps_scraper_tool_names() -> None:
    # Фаза 2: scraper включается импортом, поэтому имена тулз не неймспейсятся.
    async with Client(build_gateway()) as client:
        names = {t.name for t in await client.list_tools()}
        # Нет «scraper_»-версий поисковых тулз — контракт gateway неизменен.
        assert "scraper_search_listings" not in names
        assert "search_listings" in names
