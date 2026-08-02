"""Сборка хранилища db-сервера из переменных окружения.

db — единственный сервер, знающий про Supabase (``AVITO_SUPABASE_DSN``).
Сервер не читает `.env` — переменные передаёт шелл/агент. См. `.env.example`.
"""

from __future__ import annotations

import logging
import os

from .storage.base import ListingStore
from .storage.supabase import SupabaseStorage

log = logging.getLogger(__name__)


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

    Тип возврата — протокол, а не конкретный класс: тулзы работают через него,
    и подмена хранилища в тестах проверяется типами. ``SupabaseStorage``
    реализует ``ListingStore`` (и ``ProxyCooldownStore`` из scraper — память о
    выжженных прокси можно передавать движку).

    Raises:
        ValueError: если ``AVITO_SUPABASE_DSN`` не задан.
    """
    return _storage_from_env()