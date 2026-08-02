"""Смоук-тест notify-сервера (Фаза 4): status + send_notification."""

from fastmcp import Client

from avito_mcp_notify.server import mcp


async def test_server_instantiates_and_serves_status() -> None:
    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}
        assert "status" in tools
        assert "send_notification" in tools, "тулза уведомлений зарегистрирована"

        result = await client.call_tool("status", {})
        assert result.data == {"role": "notify", "status": "ok"}


async def test_send_notification_is_destructive_flagged() -> None:
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
    annotations = tools["send_notification"].annotations
    assert annotations is not None
    assert annotations.destructiveHint is True
