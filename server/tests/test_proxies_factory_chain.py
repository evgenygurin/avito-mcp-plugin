"""Сборка цепочки транспортов из конфигурации.

Прямое соединение ставится перед прокси по умолчанию: замер 2026-07-20 дал
200 за 0.63 с напрямую против 403 через купленную подсеть. Прокси остаётся
фоллбэком — он нужен, когда забанен уже собственный IP.
"""

from __future__ import annotations

from avito_mcp_server.proxies.factory import build_proxy
from avito_mcp_server.proxies.proxy import ChainProxy, MobileProxy, NoProxy, ServerProxy


def test_direct_goes_first_by_default() -> None:
    proxy = build_proxy("user:pass@10.0.0.1:8000", "")

    assert isinstance(proxy, ChainProxy)
    assert isinstance(proxy.links[0], NoProxy)
    assert isinstance(proxy.links[1], ServerProxy)
    assert proxy.httpx_proxy() is None


def test_mobile_proxy_keeps_its_rotation_as_the_last_link() -> None:
    proxy = build_proxy("user:pass@10.0.0.1:8000", "https://cabinet/change")

    assert isinstance(proxy, ChainProxy)
    assert isinstance(proxy.links[-1], MobileProxy)


def test_direct_first_can_be_turned_off(monkeypatch) -> None:
    # Массовый парсинг с чужого адреса: свой IP светить не нужно.
    monkeypatch.setenv("AVITO_DIRECT_FIRST", "0")

    proxy = build_proxy("user:pass@10.0.0.1:8000", "")

    assert isinstance(proxy, ServerProxy)


def test_no_proxy_configured_stays_plain_direct() -> None:
    # Без прокси городить цепочку из одного звена незачем.
    assert isinstance(build_proxy("", ""), NoProxy)


def test_pool_also_gets_the_direct_link() -> None:
    proxy = build_proxy("user:pass@10.0.0.1:8000,user:pass@10.0.0.2:8000", "")

    assert isinstance(proxy, ChainProxy)
    assert proxy.httpx_proxy() is None
