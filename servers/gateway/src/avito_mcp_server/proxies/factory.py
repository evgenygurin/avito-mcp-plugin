"""Выбор типа прокси по конфигу."""

from __future__ import annotations

import logging
import os

import httpx

from ..storage.base import ProxyCooldownStore
from .mpsapi import MpsApiProxy
from .proxy import ChainProxy, MobileProxy, NoProxy, Proxy, ProxyPool, ServerProxy

log = logging.getLogger(__name__)


def build_proxy(
    proxy: str,
    change_url: str,
    cooldown_store: ProxyCooldownStore | None = None,
    mps_api_token: str = "",
    mps_proxy_id: str = "",
    mps_operator: str = "megafone",
) -> Proxy:
    """Собрать прокси по конфигу.

    ``AVITO_PROXY`` принимает как один адрес, так и список через запятую:
    список → ``ProxyPool`` (перебор при блокировках), один адрес с ``change_url``
    → ``MobileProxy`` (ротация IP) или ``MpsApiProxy`` (ротация + эскалация
    региона/оператора через API mobileproxy.space, если заданы
    ``mps_api_token``/``mps_proxy_id``), один без него → ``ServerProxy``,
    пусто → ``NoProxy``.
    """
    urls = [part.strip() for part in proxy.split(",") if part.strip()]
    if not urls:
        # Прокси не задан — цепочка из одного прямого звена ничего не добавляет.
        return NoProxy()

    configured = _build_configured(
        urls, change_url, cooldown_store, mps_api_token, mps_proxy_id, mps_operator
    )
    if not _direct_first():
        return configured
    # Прямое соединение первым: оно и быстрее (0.63 с против таймаутов на
    # мёртвой подсети), и не тратит платные ротации. Прокси — фоллбэк на
    # случай, когда забанен уже наш собственный адрес.
    return ChainProxy([NoProxy(), configured])


def _build_configured(
    urls: list[str],
    change_url: str,
    cooldown_store: ProxyCooldownStore | None,
    mps_api_token: str,
    mps_proxy_id: str,
    mps_operator: str,
) -> Proxy:
    """Собрать тот прокси, который описан настройками, без прямого звена."""
    if len(urls) > 1:
        return ProxyPool(urls, cooldown_store=cooldown_store)
    if change_url:
        if mps_api_token and mps_proxy_id:
            return MpsApiProxy(
                urls[0], change_url, mps_api_token, mps_proxy_id, operator=mps_operator
            )
        return MobileProxy(urls[0], change_url)
    return ServerProxy(urls[0])


def _direct_first() -> bool:
    """Ставить ли прямое соединение перед прокси (``AVITO_DIRECT_FIRST``).

    По умолчанию да. Отключают, когда светить собственный адрес нельзя —
    например при массовом парсинге, где свой IP забанят на третьей странице.
    """
    raw = os.getenv("AVITO_DIRECT_FIRST", "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def fetch_proxy_list(url: str, timeout: float = 15.0) -> list[str]:
    """Забрать список прокси из кабинета провайдера (``AVITO_PROXY_LIST_URL``).

    Принимает и JSON-массив строк, и простой текст по адресу на строку. Ошибка
    сети не роняет парсинг: возвращаем пустой список, вызывающий падает на
    ``AVITO_PROXY``.
    """
    try:
        resp = httpx.get(url, timeout=timeout, trust_env=False, follow_redirects=True)
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        # InvalidURL — НЕ подкласс HTTPError (проверено в httpx 0.28.1):
        # опечатка/битый плейсхолдер в AVITO_PROXY_LIST_URL иначе пробросил бы
        # сырое исключение через build_http_client() вместо фоллбэка на
        # AVITO_PROXY.
        log.warning("не удалось получить список прокси: %s", exc)
        return []
    if resp.status_code != 200:
        log.warning("список прокси вернул статус %s", resp.status_code)
        return []
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if isinstance(payload, list):
        return [str(item).strip() for item in payload if str(item).strip()]
    return [line.strip() for line in resp.text.splitlines() if line.strip()]
