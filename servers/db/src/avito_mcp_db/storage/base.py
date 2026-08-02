"""Интерфейсы хранилища для потребителей (DIP).

Тулзы мониторинга зависят не от конкретного ``SupabaseStorage``, а от узкого
протокола с теми методами, которые им действительно нужны (ISP). Так тестовый
двойник (``tests/fakes.FakeStorage``) — не «утиная» подмена наугад, а
проверяемая типами реализация контракта.

Протокол ``ProxyCooldownStore`` (память о выжженных прокси) вынесен в scraper
(``avito_mcp_scraper.proxies.proxy``): это DIP-контракт движка, gateway не
навязывает scraper-серверу свой storage.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable

from .rows import SeenRow


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
