"""Тесты тулзы send_notification (in-memory Client)."""

from fastmcp import Client, FastMCP

import avito_mcp_server.tools.notifications as notif_mod


def _mcp() -> FastMCP:
    m = FastMCP("test")
    notif_mod.register(m)
    return m


async def test_send_notification_telegram(monkeypatch) -> None:
    def _fake_send(*args, **kwargs):
        return ("ok", True, ["123"])

    monkeypatch.setattr(notif_mod, "do_send", _fake_send)
    monkeypatch.setenv("AVITO_TG_TOKEN", "tok")
    monkeypatch.setenv("AVITO_TG_CHAT_IDS", "123")

    async with Client(_mcp()) as client:
        res = await client.call_tool(
            "send_notification", {"message": "test", "channel": "telegram"}
        )

    assert res.data.sent is True
    assert res.data.channel == "telegram"
    assert res.data.targets == ["123"]


async def test_send_notification_vk(monkeypatch) -> None:
    def _fake_send(*args, **kwargs):
        return ("ok", True, ["456"])

    monkeypatch.setattr(notif_mod, "do_send", _fake_send)
    monkeypatch.setenv("AVITO_VK_TOKEN", "tok")
    monkeypatch.setenv("AVITO_VK_USER_IDS", "456")

    async with Client(_mcp()) as client:
        res = await client.call_tool(
            "send_notification", {"message": "test", "channel": "vk"}
        )

    assert res.data.sent is True
    assert res.data.channel == "vk"


async def test_channel_schema_is_enum_not_free_string() -> None:
    # Context7-аудит: channel как голый str не несёт enum — "tg" вместо
    # "telegram" жжёт реальный вызов к Telegram/VK на ToolError вместо
    # отбоя на границе аргументов.
    async with Client(_mcp()) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "send_notification")
    channel_schema = tool.inputSchema["properties"]["channel"]
    assert set(channel_schema.get("enum", [])) == {"telegram", "vk"}
