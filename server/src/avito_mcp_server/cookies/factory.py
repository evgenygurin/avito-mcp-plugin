"""Выбор провайдера кук по конфигу (``AVITO_COOKIE_PROVIDER``)."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .base import CookiesProvider
from .own import OwnCookiesProvider
from .spfa import SpfaCookiesProvider


@dataclass(frozen=True)
class CookieSettings:
    """Всё, из чего может собираться провайдер кук.

    Один объект вместо растущего списка позиционных аргументов: каждому
    провайдеру нужна своя часть, но точка сборки — общая.
    """

    api_key: str | None = None
    own_cookies: dict[str, str] | None = None
    proxy: str | None = None


def _build_spfa(settings: CookieSettings) -> CookiesProvider:
    if not settings.api_key:
        raise ValueError("провайдер кук 'spfa' требует SPFA_API_KEY")
    return SpfaCookiesProvider(settings.api_key, cache_path=cookies_cache_path())


def _build_own(settings: CookieSettings) -> CookiesProvider:
    return OwnCookiesProvider(settings.own_cookies or {})


def _build_playwright(settings: CookieSettings) -> CookiesProvider:
    from .playwright import PlaywrightCookiesProvider

    # Тот же прокси, что и у HTTP-клиента: куки привязаны к IP, с которого
    # получены, и с другого адреса антибот их не примет.
    return PlaywrightCookiesProvider(proxy=settings.proxy)


def _build_none(settings: CookieSettings) -> CookiesProvider | None:
    """Явный отказ от кук — осознанный выбор, а не следствие опечатки."""
    return None


#: Имя из env → сборщик. Новый провайдер добавляется строкой здесь, а не
#: очередной веткой в ``build_cookies_provider``.
_PROVIDERS: dict[str, Callable[[CookieSettings], CookiesProvider | None]] = {
    "spfa": _build_spfa,
    "own": _build_own,
    "playwright": _build_playwright,
    "none": _build_none,
}


def build_cookies_provider(
    provider: str,
    *,
    api_key: str | None,
    own_cookies: dict[str, str] | None,
    proxy: str | None = None,
) -> CookiesProvider | None:
    """Собрать провайдера кук по имени из ``AVITO_COOKIE_PROVIDER``.

    ``None`` возвращается только для явного ``none``. Опечатка в имени —
    ошибка конфигурации, а не молчаливая работа без кук: без кук антибот
    отдаёт блокировки, и rotate-until-clean жжёт 18 ротаций платного прокси,
    показывая диагноз «нужен чистый RU-прокси» вместо настоящей причины.

    Raises:
        ValueError: имя провайдера неизвестно.
    """
    build = _PROVIDERS.get(provider)
    if build is None:
        supported = "|".join(_PROVIDERS)
        raise ValueError(
            f"неизвестный провайдер кук: {provider!r} (AVITO_COOKIE_PROVIDER={supported})"
        )
    return build(CookieSettings(api_key=api_key, own_cookies=own_cookies, proxy=proxy))


def cookies_cache_path() -> Path:
    """Куда класть купленные куки (``AVITO_COOKIES_CACHE``).

    Дефолт — под кэшем пользователя: куки живут ~12 часов и стоят денег, а каждый
    вызов тулзы поднимает новый процесс, поэтому кэш нужен из коробки.
    """
    raw = os.getenv("AVITO_COOKIES_CACHE", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".cache" / "avito-mcp-server" / "cookies.json"
