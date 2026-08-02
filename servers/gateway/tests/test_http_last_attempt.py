"""Последняя попытка круга не должна тратиться на бесполезную ротацию.

Смена IP через кабинет мобильного прокси стоит 3.6–4.3 с (замер 2026-07-20).
На последней попытке её результат уже никому не нужен: круг закончен, и
дальше либо эскалация (она сама меняет точку выхода), либо отказ. В сводке
``check_proxy_health`` это было ``proxy.rotate=21.3s×6`` при ``http.request=4.3s``.
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
        return _FakeSession.seq.pop(0)

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


def test_no_rotation_after_the_last_attempt(monkeypatch) -> None:
    _FakeSession.seq = [_Resp(403) for _ in range(5)]
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    proxy = _CountingProxy()
    client = HttpClient(proxy=proxy, cookies=None, max_attempts=3, wait_after_rotate=0)

    try:
        client.get("https://www.avito.ru/x")
    except RuntimeError:
        pass

    # Три попытки — две ротации между ними, третья ротация не нужна никому.
    assert proxy.rotations == 2


def test_rotation_still_happens_between_attempts(monkeypatch) -> None:
    # Проверка от обратного: пропуск не должен съесть полезную ротацию,
    # ту, после которой идёт следующая попытка.
    _FakeSession.seq = [_Resp(403), _Resp(200, "ok")]
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    proxy = _CountingProxy()
    client = HttpClient(proxy=proxy, cookies=None, max_attempts=3, wait_after_rotate=0)

    assert client.get("https://www.avito.ru/x").status_code == 200
    assert proxy.rotations == 1


class _CookiesSpy:
    """Считает вызовы, чтобы поймать «обновление кук под несуществующую попытку»."""

    def __init__(self) -> None:
        self.get_calls = 0
        self.handle_block_calls = 0

    def get(self) -> dict:
        self.get_calls += 1
        return {}

    def update(self, resp) -> None:  # noqa: ANN001
        pass

    def handle_block(self) -> None:
        self.handle_block_calls += 1


def test_no_cookie_refresh_after_the_last_attempt(monkeypatch) -> None:
    # max_attempts=5 — реальный дефолт: полный прогоревший круг даёт blocks=5
    # на последней попытке, и blocks % 5 == 0 раньше запускал платный вызов
    # spfa /unblock/ прямо в момент сдачи, когда следующей попытки уже не будет.
    _FakeSession.seq = [_Resp(403) for _ in range(5)]
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    proxy = _CountingProxy()
    cookies = _CookiesSpy()
    client = HttpClient(
        proxy=proxy, cookies=cookies, max_attempts=5, wait_after_rotate=0
    )

    try:
        client.get("https://www.avito.ru/x")
    except RuntimeError:
        pass

    # Покупка на старте + чтение перед КАЖДОЙ следующей попыткой (2..5) —
    # законно. Обновления ПОСЛЕ последней (пятой) попытки, для которой уже
    # нет следующего раунда, быть не должно.
    assert cookies.get_calls == 1 + 4
    # Принудительное обновление — на 2-й и 4-й блокировке (_COOKIE_REFRESH_EVERY),
    # то есть перед реальными попытками; пятая блокировка его не запускает.
    assert cookies.handle_block_calls == 2
