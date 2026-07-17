"""Интеграционные тесты серверного инстанса (регистрация тулз)."""

from fastmcp import Client

from avito_mcp_server.server import mcp


async def test_ping_tool_works() -> None:
    async with Client(mcp) as client:
        res = await client.call_tool("ping", {"message": "hi"})
        assert res.data.length == 2


async def test_expected_tools_are_registered() -> None:
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert {"ping", "official_api_call"} <= names
