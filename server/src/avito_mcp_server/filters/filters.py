"""Фильтрация объявлений: keyword/seller/price/geo/max_age."""

from __future__ import annotations

import time

from pydantic import BaseModel, Field

from ..models import Listing


class FilterSpec(BaseModel):
    """Параметры фильтрации. Все поля опциональны; пустой spec пропускает всё."""

    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    seller_blacklist: list[str] = Field(default_factory=list)
    price_min: float | None = None
    price_max: float | None = None
    geo: str | None = None
    max_age: int | None = None  # максимальный возраст объявления в секундах


def apply_filters(
    items: list[Listing],
    spec: FilterSpec,
    now: float | None = None,
) -> list[Listing]:
    """Оставить объявления, удовлетворяющие всем заданным критериям."""
    current = time.time() if now is None else now
    result: list[Listing] = []
    for item in items:
        title = item.title.lower()

        if spec.include_keywords and not any(
            kw.lower() in title for kw in spec.include_keywords
        ):
            continue
        if any(kw.lower() in title for kw in spec.exclude_keywords):
            continue
        if item.seller_id and item.seller_id in spec.seller_blacklist:
            continue
        if spec.price_min is not None and (
            item.price is None or item.price < spec.price_min
        ):
            continue
        if spec.price_max is not None and (
            item.price is None or item.price > spec.price_max
        ):
            continue
        if spec.geo and (
            item.address is None or spec.geo.lower() not in item.address.lower()
        ):
            continue
        if spec.max_age is not None:
            if item.published_at is None:
                continue
            if current - item.published_at / 1000 > spec.max_age:
                continue

        result.append(item)
    return result
