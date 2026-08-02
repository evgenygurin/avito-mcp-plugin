"""Единицы передачи данных в хранилище (без зависимости от драйвера БД)."""

from __future__ import annotations

from typing import NamedTuple


class SeenRow(NamedTuple):
    """Объявление для записи в ``seen_items`` — единица пакетного upsert."""

    id: int
    url: str | None
    title: str | None
    price: float | None
