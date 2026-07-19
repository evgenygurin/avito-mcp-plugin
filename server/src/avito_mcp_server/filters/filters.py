"""Фильтрация объявлений: keyword/seller/price/geo/max_age."""

from __future__ import annotations

import time
from typing import Annotated

from pydantic import BaseModel, Field

from ..models import Listing

# Общий тип параметра ``pages`` для search_listings/scan_new_listings: каждая
# страница — до AVITO_MAX_ROTATE_ATTEMPTS ротаций IP + платные spfa-куки.
# Верхняя граница отбивает ошибочный/галлюцинированный pages=500 на границе
# аргументов схемы, а не многочасовым прогоном в теле тулзы.
PageCount = Annotated[
    int,
    Field(
        ge=1,
        le=20,
        description="Сколько страниц каталога обойти (обход прекращается на последней странице сам)",
    ),
]


class FilterSpec(BaseModel):
    """Параметры фильтрации. Все поля опциональны; пустой spec пропускает всё."""

    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    seller_blacklist: list[str] = Field(default_factory=list)
    price_min: float | None = None
    price_max: float | None = None
    geo: str | None = None
    max_age: int | None = None  # максимальный возраст объявления в секундах

    @classmethod
    def from_optional(
        cls,
        *,
        include_keywords: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
        seller_blacklist: list[str] | None = None,
        price_min: float | None = None,
        price_max: float | None = None,
        geo: str | None = None,
        max_age: int | None = None,
    ) -> "FilterSpec":
        """Собрать спеку из параметров MCP-тулзы (список-фильтры приходят как ``None``).

        Тулзы (``search_listings``, ``scan_new_listings``) объявляют список-параметры
        как ``list[str] | None = None`` — FastMCP-friendly сигнатура, но ``FilterSpec``
        хочет пустой список, а не ``None``. Общая точка сборки вместо копии в каждой тулзе.
        """
        return cls(
            include_keywords=include_keywords or [],
            exclude_keywords=exclude_keywords or [],
            seller_blacklist=seller_blacklist or [],
            price_min=price_min,
            price_max=price_max,
            geo=geo,
            max_age=max_age,
        )


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
            # published_at уже в секундах — нормализуется в parser._published_at.
            if current - item.published_at > spec.max_age:
                continue

        result.append(item)
    return result
