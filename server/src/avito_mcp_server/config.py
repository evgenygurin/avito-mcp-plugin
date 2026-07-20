"""Сборка движка парсинга из переменных окружения.

Сервер не читает `.env` — переменные передаёт шелл/агент. См. `.env.example`.
"""

from __future__ import annotations

import json
import logging
import os

from sqlalchemy.exc import SQLAlchemyError

from .cookies.factory import build_cookies_provider
from .http.client import HttpClient
from .proxies.factory import build_proxy, fetch_proxy_list
from .storage.base import ListingStore, ProxyCooldownStore
from .storage.supabase import SupabaseStorage

log = logging.getLogger(__name__)

# Общий дефолт для build_http_client() и check_proxy_health (diagnostics.py) —
# при смене провайдера по умолчанию править только здесь.
DEFAULT_COOKIE_PROVIDER = "spfa"


def _parse_own_cookies(raw: str | None) -> dict[str, str]:
    """Разобрать `AVITO_OWN_COOKIES`: JSON-объект либо строку `k=v; k=v`."""
    if not raw:
        return {}
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items()}

    result: dict[str, str] = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def build_http_client() -> HttpClient:
    """Собрать `HttpClient` (провайдер кук + прокси) из окружения."""
    proxy = build_proxy(
        _proxy_setting(),
        os.getenv("AVITO_PROXY_CHANGE_URL", ""),
        cooldown_store=_optional_storage(),
    )
    provider = build_cookies_provider(
        os.getenv("AVITO_COOKIE_PROVIDER", DEFAULT_COOKIE_PROVIDER),
        api_key=os.getenv("SPFA_API_KEY"),
        own_cookies=_parse_own_cookies(os.getenv("AVITO_OWN_COOKIES")),
        proxy=proxy.httpx_proxy(),
    )
    # 18 попыток при backoff min(9*2^n, 60) — это 903с чистого сна плюс
    # таймауты, то есть тулза упиралась в собственный timeout=900 вместо
    # понятного отказа. Пять ротаций (9+18+36+60 = 123с) исчерпывают полезную
    # часть: если чистый IP не нашёлся за них, он не найдётся и за восемнадцать.
    max_attempts = int(os.getenv("AVITO_MAX_ROTATE_ATTEMPTS", "5"))
    return HttpClient(proxy=proxy, cookies=provider, max_attempts=max_attempts)


def _storage_from_env() -> SupabaseStorage:
    """Хранилище по ``AVITO_SUPABASE_DSN``.

    Raises:
        ValueError: если ``AVITO_SUPABASE_DSN`` не задан.
    """
    dsn = os.getenv("AVITO_SUPABASE_DSN", "").strip()
    if not dsn:
        raise ValueError(
            "AVITO_SUPABASE_DSN не задан — хранилище необходимо для мониторинга "
            "(Project Settings → Database → Connection string)"
        )
    return SupabaseStorage(dsn)


def build_storage() -> ListingStore:
    """Собрать хранилище (Postgres проекта Supabase) из окружения.

    Тип возврата — протокол, а не конкретный класс: тулзы мониторинга работают
    через него, и подмена хранилища в тестах проверяется типами.

    Raises:
        ValueError: если ``AVITO_SUPABASE_DSN`` не задан.
    """
    return _storage_from_env()


def page_pause() -> float:
    """Пауза между страницами каталога, сек (``AVITO_PAGE_PAUSE``, дефолт 1.0).

    Многостраничный обход без паузы выжигает IP быстрее, чем успевает собрать
    данные: Avito считает частоту запросов с адреса.
    """
    raw = os.getenv("AVITO_PAGE_PAUSE", "").strip()
    try:
        return float(raw) if raw else 1.0
    except ValueError:
        return 1.0


def _optional_storage() -> ProxyCooldownStore | None:
    """Хранилище для памяти о выжженных IP — только если БД уже настроена.

    Без ``AVITO_SUPABASE_DSN`` пул обязан работать, просто без памяти между
    запусками: ронять парсинг из-за отсутствия необязательной оптимизации нельзя.
    """
    if not os.getenv("AVITO_SUPABASE_DSN", "").strip():
        return None
    try:
        return _storage_from_env()
    except (ValueError, SQLAlchemyError) as exc:
        log.warning("память о блокировках прокси недоступна: %s", exc)
        return None


def _proxy_setting() -> str:
    """Строка прокси: сперва список из кабинета, иначе то, что задано вручную.

    ``AVITO_PROXY_LIST_URL`` избавляет от ведения списка портов в env; если
    кабинет недоступен, падаем на ``AVITO_PROXY``, а не остаёмся без прокси.
    """
    list_url = os.getenv("AVITO_PROXY_LIST_URL", "").strip()
    if list_url:
        fetched = fetch_proxy_list(list_url)
        if fetched:
            log.info("получено %s прокси из кабинета", len(fetched))
            return ",".join(fetched)
        log.warning("кабинет не отдал прокси — использую AVITO_PROXY")
    return os.getenv("AVITO_PROXY", "")
