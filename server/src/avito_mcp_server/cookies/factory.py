"""Выбор провайдера кук по конфигу."""

from __future__ import annotations

import os
from pathlib import Path

from .base import CookiesProvider
from .own import OwnCookiesProvider
from .spfa import SpfaCookiesProvider


def build_cookies_provider(
    provider: str,
    *,
    api_key: str | None,
    own_cookies: dict | None,
    proxy: str | None = None,
) -> CookiesProvider | None:
    """``spfa`` → SpfaCookiesProvider; ``own`` → OwnCookiesProvider; ``playwright`` → PlaywrightCookiesProvider."""
    if provider == "spfa":
        if not api_key:
            raise ValueError("провайдер кук 'spfa' требует SPFA_API_KEY")
        return SpfaCookiesProvider(api_key, cache_path=_cookies_cache_path())
    if provider == "own":
        return OwnCookiesProvider(own_cookies or {})
    if provider == "playwright":
        from .playwright import PlaywrightCookiesProvider

        # Тот же прокси, что и у HTTP-клиента: куки привязаны к IP, с которого
        # получены, и с другого адреса антибот их не примет.
        return PlaywrightCookiesProvider(proxy=proxy)
    return None


def _cookies_cache_path() -> Path:
    """Куда класть купленные куки (``AVITO_COOKIES_CACHE``).

    Дефолт — под кэшем пользователя: куки живут ~12 часов и стоят денег, а каждый
    вызов тулзы поднимает новый процесс, поэтому кэш нужен из коробки.
    """
    raw = os.getenv("AVITO_COOKIES_CACHE", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".cache" / "avito-mcp-server" / "cookies.json"
