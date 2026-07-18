"""Выбор типа прокси по конфигу."""

from __future__ import annotations

from .proxy import MobileProxy, NoProxy, Proxy, ServerProxy


def build_proxy(proxy: str, change_url: str) -> Proxy:
    """proxy+change_url → Mobile; только proxy → Server; иначе → NoProxy."""
    if proxy and change_url:
        return MobileProxy(proxy, change_url)
    if proxy:
        return ServerProxy(proxy)
    return NoProxy()
