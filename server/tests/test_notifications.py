"""Тесты модуля уведомлений (мок httpx.Client)."""

import httpx
import pytest

from avito_mcp_server.notifications import sender
from avito_mcp_server.notifications.sender import send_notification


class _FakeResponse:
    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload if payload is not None else {"response": 1}

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Мок ``httpx.Client``: считает создания, чтобы ловить лишние хендшейки."""

    instances: int = 0
    post_fn = staticmethod(lambda url, **kwargs: _FakeResponse())

    def __init__(self, **kwargs) -> None:
        _FakeClient.instances += 1

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *a) -> bool:  # noqa: ANN002
        return False

    def post(self, url: str, **kwargs):
        return _FakeClient.post_fn(url, **kwargs)


@pytest.fixture(autouse=True)
def _reset_fake_client(monkeypatch):
    _FakeClient.instances = 0
    _FakeClient.post_fn = staticmethod(lambda url, **kwargs: _FakeResponse())
    monkeypatch.setattr(sender.httpx, "Client", _FakeClient)


def test_telegram_sends() -> None:
    detail, sent, targets = send_notification(
        channel="telegram",
        message="test",
        token="tok",
        targets=["123"],
    )
    assert sent is True
    assert targets == ["123"]
    assert detail == "ok"


def test_vk_sends() -> None:
    detail, sent, targets = send_notification(
        channel="vk",
        message="test",
        token="tok",
        targets=["456"],
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
        send_notification(channel="telegram", message="test", token="tok")


def test_vk_requires_token() -> None:
    with pytest.raises(ValueError, match="AVITO_VK_TOKEN"):
        send_notification(channel="vk", message="test")


def test_vk_requires_user_ids() -> None:
    with pytest.raises(ValueError, match="AVITO_VK_USER_IDS"):
        send_notification(channel="vk", message="test", token="tok")


def test_vk_error_body_is_not_success() -> None:
    # VK отвечает 200 и кладёт ошибку в тело: raise_for_status() её не заметит,
    # и тулза отрапортует об отправке, которой не было.
    _FakeClient.post_fn = staticmethod(
        lambda url, **kwargs: _FakeResponse(
            {"error": {"error_code": 5, "error_msg": "User authorization failed"}}
        )
    )
    with pytest.raises(RuntimeError, match="User authorization failed"):
        send_notification(channel="vk", message="привет", token="t", targets=["1"])


def test_partial_delivery_is_reported_not_swallowed() -> None:
    # Падение на втором из трёх адресатов не отменяет доставку первому:
    # раньше тулза сообщала полный провал, и оператор слал повторно.
    calls: list[str] = []

    def _flaky_post(url: str, **kwargs):
        target = (kwargs.get("json") or {}).get("chat_id")
        calls.append(target)
        if target == "b":
            raise httpx.ConnectError("сеть отвалилась")
        return _FakeResponse({"ok": True})

    _FakeClient.post_fn = staticmethod(_flaky_post)
    detail, sent, targets = send_notification(
        channel="telegram", message="привет", token="t", targets=["a", "b", "c"]
    )

    # Обход не прерывается на первой ошибке — третий адресат тоже получает.
    assert calls == ["a", "b", "c"]
    assert targets == ["a", "c"], "в targets только реально доставленные"
    assert sent is True, "частичная доставка — не полный провал"
    assert "b" in detail


def test_uses_single_client_for_whole_batch() -> None:
    # Context7-аудит (httpx 0.28.1): раньше каждый адресат = отдельный
    # httpx.post() = отдельное TCP+TLS-рукопожатие к одному и тому же хосту.
    # Один httpx.Client на рассылку переиспользует соединение.
    send_notification(
        channel="telegram",
        message="test",
        token="tok",
        targets=["1", "2", "3"],
    )
    assert _FakeClient.instances == 1


def test_notifier_knows_its_env_variables() -> None:
    # Тулза читает env по этим именам — соответствие «канал → переменные»
    # живёт только в стратегии канала и нигде не дублируется.
    assert sender.get_notifier("telegram").token_env == "AVITO_TG_TOKEN"
    assert sender.get_notifier("telegram").targets_env == "AVITO_TG_CHAT_IDS"
    assert sender.get_notifier("vk").token_env == "AVITO_VK_TOKEN"
    assert sender.get_notifier("vk").targets_env == "AVITO_VK_USER_IDS"


def test_registry_matches_declared_channels() -> None:
    from typing import get_args

    assert set(get_args(sender.NotificationChannel)) == set(sender._NOTIFIERS)


def test_get_notifier_rejects_unknown_channel() -> None:
    with pytest.raises(ValueError, match="неподдерживаемый канал"):
        sender.get_notifier("email")
