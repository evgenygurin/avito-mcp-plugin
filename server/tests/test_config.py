"""Тесты сборки движка из переменных окружения."""

import pytest

from avito_mcp_server.config import build_http_client
from avito_mcp_server.cookies.own import OwnCookiesProvider
from avito_mcp_server.cookies.spfa import SpfaCookiesProvider
from avito_mcp_server.proxies.proxy import MobileProxy, NoProxy


def test_own_provider_and_mobile_proxy(monkeypatch) -> None:
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "own")
    monkeypatch.setenv("AVITO_OWN_COOKIES", '{"ft": "x"}')
    monkeypatch.setenv("AVITO_PROXY", "u:p@h:1")
    monkeypatch.setenv("AVITO_PROXY_CHANGE_URL", "https://chg?k=1")
    monkeypatch.setenv("AVITO_MAX_ROTATE_ATTEMPTS", "5")

    client = build_http_client()
    assert isinstance(client.cookies, OwnCookiesProvider)
    assert client.cookies.get() == {"ft": "x"}
    assert isinstance(client.proxy, MobileProxy)
    assert client.max_attempts == 5


def test_spfa_default_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("AVITO_COOKIE_PROVIDER", raising=False)
    monkeypatch.delenv("SPFA_API_KEY", raising=False)
    monkeypatch.delenv("AVITO_PROXY", raising=False)
    with pytest.raises(ValueError):
        build_http_client()


def test_spfa_with_key_no_proxy(monkeypatch) -> None:
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "spfa")
    monkeypatch.setenv("SPFA_API_KEY", "sk")
    monkeypatch.delenv("AVITO_PROXY", raising=False)
    monkeypatch.delenv("AVITO_PROXY_CHANGE_URL", raising=False)

    client = build_http_client()
    assert isinstance(client.cookies, SpfaCookiesProvider)
    assert isinstance(client.proxy, NoProxy)


def test_own_cookies_kv_format(monkeypatch) -> None:
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "own")
    monkeypatch.setenv("AVITO_OWN_COOKIES", "ft=1; foo=bar")
    monkeypatch.delenv("AVITO_PROXY", raising=False)

    client = build_http_client()
    assert isinstance(client.cookies, OwnCookiesProvider)
    assert client.cookies.get() == {"ft": "1", "foo": "bar"}
