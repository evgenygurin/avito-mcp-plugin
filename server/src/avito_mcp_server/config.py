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
from .timing import timed

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


def build_http_client(budget_scale: int = 1) -> HttpClient:
    """Собрать `HttpClient` (провайдер кук + прокси) из окружения.

    Args:
        budget_scale: во сколько раз увеличить бюджет времени — число страниц
            каталога для многостраничного обхода. Клиент один на весь обход
            (он же держит TLS-соединение), поэтому базовый потолок обрезал бы
            законный запрос на десять страниц на середине.
    """
    with timed("config.proxy", logger=log):
        proxy = build_proxy(
            _proxy_setting(),
            os.getenv("AVITO_PROXY_CHANGE_URL", ""),
            cooldown_store=_optional_storage(),
            mps_api_token=os.getenv("AVITO_MPS_API_TOKEN", ""),
            mps_proxy_id=os.getenv("AVITO_PROXY_ID", ""),
            mps_operator=os.getenv("AVITO_MPS_OPERATOR", "megafone"),
        )
    with timed("config.cookies", logger=log):
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
    max_attempts = int(os.getenv("AVITO_MAX_ROTATE_ATTEMPTS", str(DEFAULT_ATTEMPTS)))
    return HttpClient(
        proxy=proxy,
        cookies=provider,
        max_attempts=max_attempts,
        wait_after_rotate=rotate_wait(),
        budget=_scaled_budget(budget_scale),
    )


def _scaled_budget(scale: int) -> float | None:
    """Бюджет с поправкой на объём работы; ``None`` (снят) остаётся снятым."""
    base = request_budget()
    return None if base is None else base * max(1, scale)


#: Стартовая пауза после смены IP, сек. Живой прогон 2026-07-20 показал, где
#: на самом деле уходит время: ``backoff.sleep=54.0s`` и ``proxy.rotate=21.3s``
#: против ``http.request=4.3s`` полезной работы за 82-секундный вызов. Прежние
#: 9 с давали 9→18→36→60 при том, что сама ротация занимает ~4 с и уже служит
#: паузой (см. ``HttpClient._rotate_and_backoff``).
DEFAULT_ROTATE_WAIT = 3.0


#: Потолок wall-clock на один HTTP-клиент, сек. Без него бюджет вызова —
#: произведение вложенных лимитов (попытки × обновления токена × хопы ×
#: эскалация), и на прожжённом прокси тулза «висит»: живой прогон 2026-07-20
#: дал 10 запросов, 9 ротаций и 2 эскалации, когда ``timeout=180`` у тулзы уже
#: истёк. Таймаут тулзы не помогает — ``asyncio.to_thread`` не отменяется, и
#: поток продолжает жечь платные ротации в фоне.
DEFAULT_REQUEST_BUDGET = 120.0

#: Сколько комбинаций (транспорт × куки × IP) перебирать. Раньше попытка стоила
#: запрос + ротацию + экспоненциальный сон, и 18 попыток превращались в четверть
#: часа. Теперь сон остался только для 429, попытка стоит ~6 с (0.7 запрос +
#: ~5 ротация), и в бюджет 120 с их влезает полтора десятка. Живой прогон
#: 2026-07-20 упирался именно в лимит попыток («6 из 6»), а не в бюджет: чистый
#: IP ищется перебором, и обрывать перебор раньше времени — значит не найти его.
DEFAULT_ATTEMPTS = 12


def request_budget() -> float | None:
    """Бюджет времени на HTTP-клиент (``AVITO_REQUEST_BUDGET``, сек).

    ``0`` или отрицательное — снять ограничение (для скриптов, которым важнее
    дождаться результата, чем ответить вовремя).
    """
    raw = os.getenv("AVITO_REQUEST_BUDGET", "").strip()
    if not raw:
        return DEFAULT_REQUEST_BUDGET
    try:
        value = float(raw)
    except ValueError:
        log.warning(
            "AVITO_REQUEST_BUDGET=%r не число — беру %s", raw, DEFAULT_REQUEST_BUDGET
        )
        return DEFAULT_REQUEST_BUDGET
    return value if value > 0 else None


def rotate_wait() -> float:
    """Стартовая пауза после ротации IP (``AVITO_ROTATE_WAIT``, сек).

    Опечатка или мусор в переменной не должны ронять парсинг — падаем на
    дефолт. Ноль и отрицательные значения — законное «не спать вовсе».
    """
    raw = os.getenv("AVITO_ROTATE_WAIT", "").strip()
    if not raw:
        return DEFAULT_ROTATE_WAIT
    try:
        return max(0.0, float(raw))
    except ValueError:
        log.warning("AVITO_ROTATE_WAIT=%r не число — беру %s", raw, DEFAULT_ROTATE_WAIT)
        return DEFAULT_ROTATE_WAIT


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
        with timed("config.proxy_list", logger=log):
            fetched = fetch_proxy_list(list_url)
        if fetched:
            log.info("получено %s прокси из кабинета", len(fetched))
            return ",".join(fetched)
        log.warning("кабинет не отдал прокси — использую AVITO_PROXY")
    return os.getenv("AVITO_PROXY", "")
