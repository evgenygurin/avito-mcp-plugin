"""Интерфейсы хранилища для потребителей (DIP).

Пул прокси и тулзы зависят не от конкретного ``SupabaseStorage``, а от узкого
протокола с теми методами, которые им действительно нужны (ISP). Так тестовый
двойник (``tests/fakes.FakeStorage``) — не «утиная» подмена наугад, а
проверяемая типами реализация контракта.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable

from .rows import SeenRow


@runtime_checkable
class ProxyCooldownStore(Protocol):
    """Память о выжженных прокси между запусками."""

    def mark_proxy_blocked(self, proxy: str) -> None:
        """Запомнить адрес, отдавший блокировку."""
        ...

    def blocked_proxies(self, ttl: float) -> set[str]:
        """Адреса, заблокированные не позже ``ttl`` секунд назад."""
        ...


@runtime_checkable
class ListingStore(Protocol):
    """Состояние мониторинга: что уже видели и как менялась цена."""

    def fetch_seen(self, item_ids: Iterable[int]) -> dict[int, float | None]:
        """``{id: последняя цена}`` для известных объявлений из запрошенных."""
        ...

    def upsert_seen_many(self, rows: Sequence[SeenRow]) -> None:
        """Записать пачку объявлений и дописать историю цены."""
        ...

    def get_price_history(self, item_id: int) -> list[tuple[float, float]]:
        """История цены, свежая первой: список ``(цена, время)``."""
        ...
