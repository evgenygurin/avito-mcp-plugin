"""Лечение блокировки — по возрастанию цены, а не сразу самым дорогим.

Замеры 2026-07-20 дали прайс-лист средств против 403:

    смена транспорта (ChainProxy)   ~0 с
    свежие куки spfa                ~0.6 с
    ротация IP через кабинет        ~5 с

При этом решают задачу они примерно одинаково часто: в одном прогоне 200
пришли на свежих куках, в другом — после смены выходного адреса. Прежний код
дёргал ротацию на КАЖДОЙ блокировке, а куки — на каждой второй, и профиль
получался соответствующий: ``proxy.rotate=96.9s×19`` против ``http.request``
19.9 с полезной работы, то есть 78% времени вызова уходило в самое дорогое
лекарство.

Отсюда чередование: на нечётной блокировке пробуем дешёвое (куки), на чётной —
дорогое (смена адреса). Число ротаций падает вдвое при том же числе попыток.
"""

from __future__ import annotations

import avito_mcp_server.http.client as hc
from avito_mcp_server.http.client import HttpClient


class _Resp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeSession:
    seq: list = []

    def get(self, url, cookies=None, timeout=None, allow_redirects=True):  # noqa: ANN001, ANN201
        return _FakeSession.seq.pop(0) if _FakeSession.seq else _Resp(403)

    def close(self) -> None:
        pass


class _CountingProxy:
    def __init__(self) -> None:
        self.rotations = 0

    def httpx_proxy(self) -> str:
        return "http://x"

    def rotate(self) -> bool:
        self.rotations += 1
        return True


class _CountingCookies:
    def __init__(self) -> None:
        self.refreshes = 0

    def get(self) -> dict:
        return {}

    def update(self, resp) -> None:  # noqa: ANN001
        pass

    def handle_block(self) -> None:
        self.refreshes += 1


def _run(monkeypatch, attempts: int):
    _FakeSession.seq = [_Resp(403) for _ in range(attempts)]
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    proxy, cookies = _CountingProxy(), _CountingCookies()
    client = HttpClient(
        proxy=proxy, cookies=cookies, max_attempts=attempts, wait_after_rotate=0
    )
    try:
        client.get("https://www.avito.ru/x")
    except RuntimeError:
        pass
    return proxy, cookies


def test_expensive_rotation_is_not_used_on_every_block(monkeypatch) -> None:
    proxy, _ = _run(monkeypatch, attempts=8)

    # Восемь блокировок — заметно меньше восьми ротаций: дорогое средство
    # чередуется с дешёвым, а не применяется каждый раз.
    assert proxy.rotations < 8


def test_cheap_cookie_refresh_is_used_at_least_as_often(monkeypatch) -> None:
    proxy, cookies = _run(monkeypatch, attempts=8)

    assert cookies.refreshes >= proxy.rotations


def test_both_remedies_are_actually_tried(monkeypatch) -> None:
    # Ни одно из средств не должно выпасть совсем: 403 приходит по обеим
    # причинам, и лечение только одной оставляет половину случаев непокрытой.
    proxy, cookies = _run(monkeypatch, attempts=6)

    assert proxy.rotations >= 1
    assert cookies.refreshes >= 1
