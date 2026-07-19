"""Тесты модуля уведомлений (мок httpx)."""

import httpx
import pytest

from avito_mcp_server.notifications.sender import send_notification


class _FakeResponse:
    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload if payload is not None else {"response": 1}

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


def _fake_post(url: str, **kwargs):
    return _FakeResponse()


def test_telegram_sends(monkeypatch) -> None:
    monkeypatch.setattr("avito_mcp_server.notifications.sender.httpx.post", _fake_post)
    detail, sent, targets = send_notification(
        channel="telegram",
        message="test",
        tg_token="tok",
        tg_chat_ids=["123"],
    )
    assert sent is True
    assert targets == ["123"]
    assert detail == "ok"


def test_vk_sends(monkeypatch) -> None:
    monkeypatch.setattr("avito_mcp_server.notifications.sender.httpx.post", _fake_post)
    detail, sent, targets = send_notification(
        channel="vk",
        message="test",
        vk_token="tok",
        vk_user_ids=["456"],
    )
    assert sent is True
    assert targets == ["456"]


def test_unknown_channel_raises() -> None:
    with pytest.raises(ValueError, match="неподдерживаемый канал"):
        send_notification(channel="email", message="test")


def test_telegram_requires_token() -> None:
    with pytest.raises(ValueError, match="AVITO_TG_TOKEN"):
        send_notification(channel="telegram", message="test")


def test_telegram_requires_chat_ids() -> None:
    with pytest.raises(ValueError, match="AVITO_TG_CHAT_IDS"):
        send_notification(channel="telegram", message="test", tg_token="tok")


def test_vk_requires_token() -> None:
    with pytest.raises(ValueError, match="AVITO_VK_TOKEN"):
        send_notification(channel="vk", message="test")


def test_vk_requires_user_ids() -> None:
    with pytest.raises(ValueError, match="AVITO_VK_USER_IDS"):
        send_notification(channel="vk", message="test", vk_token="tok")


def test_vk_error_body_is_not_success(monkeypatch) -> None:
    # VK отвечает 200 и кладёт ошибку в тело: raise_for_status() её не заметит,
    # и тулза отрапортует об отправке, которой не было.
    def _error_post(url: str, **kwargs):
        return _FakeResponse(
            {"error": {"error_code": 5, "error_msg": "User authorization failed"}}
        )

    monkeypatch.setattr("avito_mcp_server.notifications.sender.httpx.post", _error_post)
    with pytest.raises(RuntimeError, match="User authorization failed"):
        send_notification(
            channel="vk", message="привет", vk_token="t", vk_user_ids=["1"]
        )


def test_partial_delivery_is_reported_not_swallowed(monkeypatch) -> None:
    # Падение на втором из трёх адресатов не отменяет доставку первому:
    # раньше тулза сообщала полный провал, и оператор слал повторно.
    calls: list[str] = []

    def _flaky_post(url: str, **kwargs):
        target = (kwargs.get("json") or {}).get("chat_id")
        calls.append(target)
        if target == "b":
            raise httpx.ConnectError("сеть отвалилась")
        return _FakeResponse({"ok": True})

    monkeypatch.setattr("avito_mcp_server.notifications.sender.httpx.post", _flaky_post)
    detail, sent, targets = send_notification(
        channel="telegram", message="привет", tg_token="t", tg_chat_ids=["a", "b", "c"]
    )

    # Обход не прерывается на первой ошибке — третий адресат тоже получает.
    assert calls == ["a", "b", "c"]
    assert targets == ["a", "c"], "в targets только реально доставленные"
    assert sent is True, "частичная доставка — не полный провал"
    assert "b" in detail
