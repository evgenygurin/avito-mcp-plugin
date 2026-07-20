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
