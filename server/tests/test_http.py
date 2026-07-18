"""Тесты HTTP-клиента: rotate-until-clean + follow-редирект (мок сессии)."""

from pathlib import Path

import pytest

import avito_mcp_server.http.client as hc
from avito_mcp_server.http.client import HttpClient, fetch_catalog

FIX = Path(__file__).parent / "fixtures"


class _Resp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeSession:
    seq: list = []

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *a) -> bool:  # noqa: ANN002
        return False

    def get(self, url, cookies=None, timeout=None, allow_redirects=True):  # noqa: ANN001
        return _FakeSession.seq.pop(0)


class _FakeProxy:
    def __init__(self) -> None:
        self.rotations = 0

    def httpx_proxy(self) -> str:
        return "http://x"

    def rotate(self) -> bool:
        self.rotations += 1
        return True


def test_rotate_until_clean(monkeypatch) -> None:
    _FakeSession.seq = [_Resp(403), _Resp(403), _Resp(200, "<html>ok</html>")]
    monkeypatch.setattr(hc, "_build_session", lambda proxy_url: _FakeSession())
    proxy = _FakeProxy()
    client = HttpClient(proxy=proxy, cookies=None, max_attempts=5, wait_after_rotate=0)
    resp = client.get("https://www.avito.ru/x")
    assert resp.status_code == 200
    assert proxy.rotations == 2  # ротация на каждый из двух 403


def test_get_raises_after_max_attempts(monkeypatch) -> None:
    _FakeSession.seq = [_Resp(403) for _ in range(10)]
    monkeypatch.setattr(hc, "_build_session", lambda proxy_url: _FakeSession())
    client = HttpClient(
        proxy=_FakeProxy(), cookies=None, max_attempts=3, wait_after_rotate=0
    )
    with pytest.raises(RuntimeError):
        client.get("https://www.avito.ru/x")


def test_fetch_catalog_follows_redirect() -> None:
    stub = (FIX / "redirect_stub.html").read_text(encoding="utf-8")
    catalog = (FIX / "catalog.html").read_text(encoding="utf-8")
    pages = [_Resp(200, stub), _Resp(200, catalog)]

    class _Client:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def get(self, url: str) -> _Resp:
            self.urls.append(url)
            return pages.pop(0)

    client = _Client()
    kind, payload = fetch_catalog(
        client, "https://www.avito.ru/nizhniy_novgorod/kvartiry/prodam"
    )
    assert kind == "ok"
    assert isinstance(payload, dict) and payload.get("items")
    assert len(client.urls) == 2  # исходный + канонический после редиректа
