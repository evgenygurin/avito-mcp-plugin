"""Тесты тулзы send_notification (in-memory Client)."""

from fastmcp import Client, FastMCP

import avito_mcp_server.tools.notifications as notif_mod
from avito_mcp_server.notifications.sender import DeliveryReport


def _mcp() -> FastMCP:
    m = FastMCP("test")
    notif_mod.register(m)
    return m


async def test_send_notification_telegram(monkeypatch) -> None:
    def _fake_send(*args, **kwargs):
        return DeliveryReport(detail="ok", delivered=["123"], failed=[])

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
        return DeliveryReport(detail="ok", delivered=["456"], failed=[])

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


async def test_explicit_targets_win_over_env(monkeypatch) -> None:
    # Явные адресаты обязаны победить env: иначе сообщение уходит не тем людям,
    # а тулза рапортует об успехе.
    captured: dict = {}

    def _fake_send(*, channel, message, token, targets):
        captured.update(channel=channel, token=token, targets=targets)
        return DeliveryReport(detail="ok", delivered=targets, failed=[])

    monkeypatch.setattr(notif_mod, "do_send", _fake_send)
    monkeypatch.setenv("AVITO_TG_TOKEN", "tok")
    monkeypatch.setenv("AVITO_TG_CHAT_IDS", "111,222")

    async with Client(_mcp()) as client:
        res = await client.call_tool(
            "send_notification",
            {"message": "test", "channel": "telegram", "targets": ["999"]},
        )

    assert captured["targets"] == ["999"], "env-адресаты должны быть проигнорированы"
    assert res.data.targets == ["999"]


async def test_vk_channel_reads_its_own_env(monkeypatch) -> None:
    captured: dict = {}

    def _fake_send(*, channel, message, token, targets):
        captured.update(token=token, targets=targets)
        return DeliveryReport(detail="ok", delivered=targets, failed=[])

    monkeypatch.setattr(notif_mod, "do_send", _fake_send)
    monkeypatch.setenv("AVITO_TG_TOKEN", "tg-token")
    monkeypatch.setenv("AVITO_TG_CHAT_IDS", "111")
    monkeypatch.setenv("AVITO_VK_TOKEN", "vk-token")
    monkeypatch.setenv("AVITO_VK_USER_IDS", "456")

    async with Client(_mcp()) as client:
        await client.call_tool("send_notification", {"message": "x", "channel": "vk"})

    assert captured == {"token": "vk-token", "targets": ["456"]}
