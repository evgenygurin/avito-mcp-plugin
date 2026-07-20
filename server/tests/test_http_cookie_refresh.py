"""Свежие куки — самое дешёвое лекарство от 403, и пробовать его надо рано.

Замеры 2026-07-20 показали, что 403 приходит по двум независимым причинам, и
они меняются местами в течение получаса:

    12:20  свежие куки, direct -> 200      прокси -> 403   (подсеть забанена)
    12:36  те же куки, direct  -> 403      прокси -> 403   (куки выгорели)
    12:40  СВЕЖИЕ куки, direct -> 403      прокси -> 200   (забанен наш IP)

Цена лечения несопоставима: покупка кук — 0.6 с, ротация IP через кабинет —
3.6–4.3 с, а прежний код обновлял куки только на КАЖДОЙ ПЯТОЙ блокировке,
то есть уже после того, как бюджет времени практически выбран.
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


class _Cookies:
    def __init__(self) -> None:
        self.refreshes = 0

    def get(self) -> dict:
        return {}

    def update(self, resp) -> None:  # noqa: ANN001
        pass

    def handle_block(self) -> None:
        self.refreshes += 1


class _RotatingProxy:
    def httpx_proxy(self) -> str:
        return "http://x"

    def rotate(self) -> bool:
        return True


def test_cookies_refreshed_early_not_on_the_fifth_block(monkeypatch) -> None:
    _FakeSession.seq = [_Resp(403) for _ in range(4)]
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    cookies = _Cookies()
    client = HttpClient(
        proxy=_RotatingProxy(), cookies=cookies, max_attempts=4, wait_after_rotate=0
    )

    try:
        client.get("https://www.avito.ru/x")
    except RuntimeError:
        pass

    # За четыре попытки куки обязаны обновиться хотя бы раз: ждать пятой
    # блокировки — значит потратить весь бюджет на заведомо мёртвые куки.
    assert cookies.refreshes >= 1


def test_cookie_refresh_is_not_done_on_every_single_block(monkeypatch) -> None:
    # Обратная крайность: каждая покупка стоит денег, поэтому обновлять на
    # КАЖДОЙ блокировке тоже неверно — сначала бесплатная смена транспорта.
    _FakeSession.seq = [_Resp(403) for _ in range(6)]
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    cookies = _Cookies()
    client = HttpClient(
        proxy=_RotatingProxy(), cookies=cookies, max_attempts=6, wait_after_rotate=0
    )

    try:
        client.get("https://www.avito.ru/x")
    except RuntimeError:
        pass

    assert cookies.refreshes < 6
