"""Тесты контрактов хранилища (storage/base.py).

Потребители (пул прокси, тулзы мониторинга) зависят от узких протоколов, а не
от конкретного ``SupabaseStorage``. Здесь проверяется, что и рабочая
реализация, и тестовый двойник этим протоколам соответствуют — иначе подмена в
тестах «зелёная», а прод падает на отсутствующем методе.
"""

from fakes import FakeStorage

from avito_mcp_server.storage.base import ListingStore, ProxyCooldownStore
from avito_mcp_server.storage.supabase import SupabaseStorage


def test_fake_storage_implements_both_protocols() -> None:
    fake = FakeStorage()
    assert isinstance(fake, ListingStore)
    assert isinstance(fake, ProxyCooldownStore)


def test_supabase_storage_implements_both_protocols() -> None:
    # runtime_checkable-протокол сверяет наличие методов, без подключения к БД.
    assert issubclass(SupabaseStorage, ListingStore)
    assert issubclass(SupabaseStorage, ProxyCooldownStore)


def test_protocol_signatures_are_checked_by_mypy() -> None:
    # isinstance у runtime_checkable-протокола сверяет ТОЛЬКО имена методов —
    # арность и типы игнорирует. Присваивание в аннотированную переменную даёт
    # точку, где сигнатуры сверит mypy.
    fake_listings: ListingStore = FakeStorage()
    fake_cooldown: ProxyCooldownStore = FakeStorage()
    real: ListingStore = SupabaseStorage.__new__(SupabaseStorage)

    assert fake_listings.fetch_seen([]) == {}
    assert fake_cooldown.blocked_proxies(1.0) == set()
    assert real is not None
