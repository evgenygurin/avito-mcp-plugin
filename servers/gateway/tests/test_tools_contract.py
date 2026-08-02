"""Контрактный тест Фазы 6: внешние имена/сигнатуры 7 тулз gateway.

После разбиения монолита (Фазы 1–5) внешний контракт клиента не должен был
измениться: ровно эти 7 тулз доступны через gateway под теми же именами
(без неймспейс-префиксов scraper_/db_/notify_ у канонических тулз), и у каждой
есть JSON-schema сигнатуры (inputSchema), как у тулз до рефакторинга.
"""

from fastmcp import Client

from avito_mcp_server.gateway import build_gateway

# Канонический контракт: имена тулз, которые клиент вызывал до разбиения.
CONTRACT_TOOLS = (
    "search_listings",
    "get_listing",
    "check_proxy_health",
    "scan_new_listings",
    "get_price_history",
    "export_listings",
    "send_notification",
)


async def test_gateway_exposes_all_7_contract_tools() -> None:
    async with Client(build_gateway()) as client:
        names = {t.name for t in await client.list_tools()}
    missing = set(CONTRACT_TOOLS) - names
    assert not missing, f"не хватает контрактных тулз: {missing}"


async def test_contract_tools_keep_canonical_names() -> None:
    # Неймспейсятся только прокси-скелеты db/notify (db_status и т.п.);
    # каноничные 7 тулз — под чистыми именами.
    async with Client(build_gateway()) as client:
        names = {t.name for t in await client.list_tools()}
    for tool in CONTRACT_TOOLS:
        assert tool in names, tool
        for prefix in ("scraper_", "db_", "notify_"):
            assert not tool.startswith(prefix), (
                f"контрактная тулза {tool} не должна иметь префикс {prefix!r}"
            )


async def test_contract_tools_have_input_schema() -> None:
    async with Client(build_gateway()) as client:
        tools = {t.name: t for t in await client.list_tools()}
    for name in CONTRACT_TOOLS:
        tool = tools[name]
        schema = getattr(tool, "inputSchema", None)
        assert schema, f"{name}: отсутствует inputSchema"
        assert isinstance(schema, dict), f"{name}: inputSchema не объект"
        assert "type" in schema, f"{name}: inputSchema без type"
