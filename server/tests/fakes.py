"""Тестовые двойники внешних зависимостей.

``FakeStorage`` повторяет интерфейс ``SupabaseStorage`` в памяти процесса: тулзы
проверяются без сети и без второй СУБД, а поведение хранилища как таковое —
в ``test_storage_supabase.py`` против настоящего Postgres.
"""

from __future__ import annotations

import time


class FakeStorage:
    """Хранилище в памяти с интерфейсом SupabaseStorage."""

    def __init__(self) -> None:
        self.items: dict[int, dict] = {}
        self.history: dict[int, list[tuple[float, float]]] = {}
        self.cooldown: dict[str, float] = {}

    def upsert_seen(
        self,
        item_id: int,
        url: str | None,
        title: str | None,
        price: float | None,
    ) -> bool:
        is_new = item_id not in self.items
        now = time.time()
        self.items[item_id] = {
            "url": url,
            "title": title,
            "price": price,
            "last_seen": now,
        }
        if price is not None:
            self.history.setdefault(item_id, []).insert(0, (float(price), now))
        return is_new

    def get_previous_price(self, item_id: int) -> float | None:
        item = self.items.get(item_id)
        return None if item is None else item["price"]

    def list_seen_ids(self) -> set[int]:
        return set(self.items)

    def get_price_history(self, item_id: int) -> list[tuple[float, float]]:
        return list(self.history.get(item_id, []))

    def mark_proxy_blocked(self, proxy: str) -> None:
        self.cooldown[proxy] = time.time()

    def blocked_proxies(self, ttl: float) -> set[str]:
        cutoff = time.time() - ttl
        return {proxy for proxy, at in self.cooldown.items() if at > cutoff}

    def forget_proxy(self, proxy: str) -> None:
        self.cooldown.pop(proxy, None)
