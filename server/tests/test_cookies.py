"""Тесты провайдеров кук (spfa/own) с мокнутым httpx."""

import avito_mcp_server.cookies.spfa as spfa_mod
from avito_mcp_server.cookies.factory import build_cookies_provider
from avito_mcp_server.cookies.own import OwnCookiesProvider
from avito_mcp_server.cookies.spfa import SpfaCookiesProvider


class _Resp:
    def __init__(self, code: int, payload: dict | None = None) -> None:
        self.status_code = code
        self._p = payload or {}

    def json(self) -> dict:
        return self._p

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def test_spfa_buys_cookies(monkeypatch) -> None:
    seen: dict = {}

    def fake_post(url, json, headers, timeout):  # noqa: ANN001
        seen["url"] = url
        seen["body"] = json
        return _Resp(200, {"results": {"id": "144514", "cookies": {"ft": "1"}}})

    monkeypatch.setattr(spfa_mod.httpx, "post", fake_post)
    p = SpfaCookiesProvider(api_key="sk_test")
    assert p.get() == {"ft": "1"}
    assert p.last_id == "144514"
    assert seen["url"].endswith("/api/cookies/")
    assert seen["body"] == {"api_key": "sk_test"}

    # Повторный get не покупает заново — использует кэш.
    monkeypatch.setattr(
        spfa_mod.httpx,
        "post",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("re-buy!")),
    )
    assert p.get() == {"ft": "1"}


def test_spfa_handle_block_rebuys_when_unblock_fails(monkeypatch) -> None:
    posts: list[str] = []

    def fake_post(url, json, headers, timeout):  # noqa: ANN001
        posts.append(url)
        if url.endswith("/unblock/"):
            return _Resp(410)  # истёк срок — нужна покупка новых
        return _Resp(200, {"results": {"id": "new", "cookies": {"ft": "2"}}})

    monkeypatch.setattr(spfa_mod.httpx, "post", fake_post)
    p = SpfaCookiesProvider(api_key="sk")
    p.last_id = "old"
    p.last_cookies = {"ft": "old"}
    p.handle_block()
    assert p.last_cookies == {"ft": "2"}
    assert any(u.endswith("/unblock/") for u in posts)


def test_own_provider_returns_fixed_cookies() -> None:
    p = OwnCookiesProvider({"ft": "mine"})
    assert p.get() == {"ft": "mine"}
    p.handle_block()  # no-op, не падает


def test_factory_selects_provider() -> None:
    assert isinstance(
        build_cookies_provider("spfa", api_key="k", own_cookies=None),
        SpfaCookiesProvider,
    )
    assert isinstance(
        build_cookies_provider("own", api_key=None, own_cookies={"ft": "x"}),
        OwnCookiesProvider,
    )
    assert build_cookies_provider("none", api_key=None, own_cookies=None) is None
