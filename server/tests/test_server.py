"""Интеграционные тесты серверного инстанса (регистрация тулз)."""

from fastmcp import Client

from avito_mcp_server.server import mcp


async def test_server_instantiates_and_serves_skills() -> None:
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
        # Парсинг-тулзы зарегистрированы.
        assert {"search_listings", "check_proxy_health"} <= names
        # Удалённых тулз официального API нет.
        assert names.isdisjoint(
            {"ping", "official_api_call", "get_own_items", "get_account_info"}
        )
        resources = await client.list_resources()
        assert any(str(r.uri).startswith("skill://") for r in resources)
