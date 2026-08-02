"""Смоук-тест notify-скелета (Фаза 1)."""

from fastmcp import Client

from avito_mcp_notify.server import mcp


async def test_server_instantiates_and_serves_status() -> None:
    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}
        assert "status" in tools

        result = await client.call_tool("status", {})
        assert result.data == {"role": "notify", "status": "ok"}
