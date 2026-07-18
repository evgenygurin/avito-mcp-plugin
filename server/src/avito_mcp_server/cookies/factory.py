"""Выбор провайдера кук по конфигу."""

from __future__ import annotations

from .base import CookiesProvider
from .own import OwnCookiesProvider
from .spfa import SpfaCookiesProvider


def build_cookies_provider(
    provider: str,
    *,
    api_key: str | None,
    own_cookies: dict | None,
) -> CookiesProvider | None:
    """`spfa` → SpfaCookiesProvider; `own` → OwnCookiesProvider; иначе None."""
    if provider == "spfa":
        if not api_key:
            raise ValueError("провайдер кук 'spfa' требует SPFA_API_KEY")
        return SpfaCookiesProvider(api_key)
    if provider == "own":
        return OwnCookiesProvider(own_cookies or {})
    return None
