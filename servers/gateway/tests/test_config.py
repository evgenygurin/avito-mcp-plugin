"""Тесты сборки хранилища gateway из окружения (Фаза 2).

Dвижок-конфиг (прокси/куки/HTTP) живёт в scraper; gateway здесь собирает только
Postgres-хранилище (``build_storage``). Движковые тесты конфигурации — в
``scraper/tests/test_config.py``.
"""

import pytest

from avito_mcp_server.config import build_storage
from avito_mcp_server.storage.supabase import SupabaseStorage


def test_build_storage_returns_supabase(monkeypatch) -> None:
    monkeypatch.setenv("AVITO_SUPABASE_DSN", "postgresql://u:p@h:5432/postgres")
    storage = build_storage()
    assert isinstance(storage, SupabaseStorage)


def test_build_storage_requires_dsn(monkeypatch) -> None:
    monkeypatch.delenv("AVITO_SUPABASE_DSN", raising=False)
    with pytest.raises(ValueError, match="AVITO_SUPABASE_DSN"):
        build_storage()
