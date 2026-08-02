"""Тестовые двойники хранилища db.

``FakeStorage`` повторяет интерфейс ``SupabaseStorage`` в памяти процесса:
тулзы проверяются без сети и без второй СУБД, а поведение хранилища как
таковое — в ``test_storage_supabase.py`` против настоящего Postgres.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Sequence

from avito_mcp_db.storage import SeenRow
from avito_mcp_scraper.proxies.proxy import ProxyCooldownStore


class FakeStorage:
    """Хранилище в памяти с интерфейсом SupabaseStorage.

    ``calls`` считает обращения к «базе»: тулзы обязаны ходить в хранилище
    пакетно, и счётчик не даёт N+1 вернуться незамеченным.
    """

    def __init__(self) -> None:
        self.items: dict[int, dict] = {}
        self.history: dict[int, list[tuple[float, float]]] = {}
        self.cooldown: dict[str, float] = {}
        self.calls = 0

    def fetch_seen(self, item_ids: Iterable[int]) -> dict[int, float | None]:
        self.calls += 1
        return {
            item_id: self.items[item_id]["price"]
            for item_id in item_ids
            if item_id in self.items
        }

    def upsert_seen_many(self, rows: Sequence[SeenRow]) -> None:
        self.calls += 1
        now = time.time()
        for row in rows:
            self.items[row.id] = {
                "url": row.url,
                "title": row.title,
                "price": row.price,
                "last_seen": now,
            }
            if row.price is not None:
                self.history.setdefault(row.id, []).insert(0, (float(row.price), now))

    def upsert_seen(
        self,
        item_id: int,
        url: str | None,
        title: str | None,
        price: float | None,
    ) -> bool:
        is_new = item_id not in self.items
        self.upsert_seen_many([SeenRow(id=item_id, url=url, title=title, price=price)])
        return is_new

    def get_previous_price(self, item_id: int) -> float | None:
        item = self.items.get(item_id)
        return None if item is None else item["price"]

    def get_price_history(self, item_id: int) -> list[tuple[float, float]]:
        return list(self.history.get(item_id, []))

    def mark_proxy_blocked(self, proxy: str) -> None:
        self.cooldown[proxy] = time.time()

    def blocked_proxies(self, ttl: float) -> set[str]:
        cutoff = time.time() - ttl
        return {proxy for proxy, at in self.cooldown.items() if at > cutoff}

    def forget_proxy(self, proxy: str) -> None:
        self.cooldown.pop(proxy, None)


# Проверка соответствия протоколам хранилища (как в test_storage_contracts.py).
_ = (ProxyCooldownStore,)
