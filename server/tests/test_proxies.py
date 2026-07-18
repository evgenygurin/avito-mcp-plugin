"""Тесты прокси-слоя (mobile/server/none + ротация IP)."""

import avito_mcp_server.proxies.proxy as proxy_mod
from avito_mcp_server.proxies.factory import build_proxy
from avito_mcp_server.proxies.proxy import MobileProxy, NoProxy, ServerProxy


def test_factory_mobile_when_change_url() -> None:
    p = build_proxy(proxy="u:p@h:1", change_url="https://chg?k=1")
    assert isinstance(p, MobileProxy)
    assert p.httpx_proxy() == "http://u:p@h:1"


def test_factory_server_when_no_change_url() -> None:
    assert isinstance(build_proxy(proxy="u:p@h:1", change_url=""), ServerProxy)


def test_factory_none_when_empty() -> None:
    p = build_proxy(proxy="", change_url="")
    assert isinstance(p, NoProxy)
    assert p.httpx_proxy() is None


def test_mobile_rotate_ok(monkeypatch) -> None:
    called: dict = {}

    class _R:
        status_code = 200

        def json(self) -> dict:
            return {"new_ip": "1.2.3.4"}

    def fake_get(url, timeout):  # noqa: ANN001
        called["url"] = url
        return _R()

    monkeypatch.setattr(proxy_mod.httpx, "get", fake_get)
    assert MobileProxy("u:p@h:1", "https://chg?k=1").rotate() is True
    assert "format=json" in called["url"]


def test_server_rotate_is_noop() -> None:
    assert ServerProxy("u:p@h:1").rotate() is False
