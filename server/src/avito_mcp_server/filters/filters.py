"""Фильтрация объявлений: keyword/seller/price/geo/max_age.

Каждый критерий — самостоятельный предикат ``(listing, spec, now) -> bool``
(Specification): объявление проходит, если его пропустили все предикаты.
Новый критерий добавляется функцией и строкой в ``_CRITERIA``, а не ещё одним
``continue`` внутри общего цикла.
"""

from __future__ import annotations

import time
from collections.abc import Callable
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


#: Критерий: пропустить объявление? ``now`` — момент отсчёта для возраста.
Criterion = Callable[[Listing, FilterSpec, float], bool]


def _matches_include(item: Listing, spec: FilterSpec, now: float) -> bool:
    if not spec.include_keywords:
        return True
    title = item.title.lower()
    return any(kw.lower() in title for kw in spec.include_keywords)


def _matches_exclude(item: Listing, spec: FilterSpec, now: float) -> bool:
    title = item.title.lower()
    return not any(kw.lower() in title for kw in spec.exclude_keywords)


def _seller_allowed(item: Listing, spec: FilterSpec, now: float) -> bool:
    return not (item.seller_id and item.seller_id in spec.seller_blacklist)


def _price_in_range(item: Listing, spec: FilterSpec, now: float) -> bool:
    # Объявление без цены не может доказать, что попадает в диапазон.
    if spec.price_min is not None and (
        item.price is None or item.price < spec.price_min
    ):
        return False
    if spec.price_max is not None and (
        item.price is None or item.price > spec.price_max
    ):
        return False
    return True


def _geo_matches(item: Listing, spec: FilterSpec, now: float) -> bool:
    if not spec.geo:
        return True
    return item.address is not None and spec.geo.lower() in item.address.lower()


def _fresh_enough(item: Listing, spec: FilterSpec, now: float) -> bool:
    if spec.max_age is None:
        return True
    if item.published_at is None:
        return False
    # published_at уже в секундах — нормализуется в parser.mapping._published_at.
    return now - item.published_at <= spec.max_age


_CRITERIA: tuple[Criterion, ...] = (
    _matches_include,
    _matches_exclude,
    _seller_allowed,
    _price_in_range,
    _geo_matches,
    _fresh_enough,
)


def apply_filters(
    items: list[Listing],
    spec: FilterSpec,
    now: float | None = None,
) -> list[Listing]:
    """Оставить объявления, удовлетворяющие всем заданным критериям."""
    current = time.time() if now is None else now
    return [
        item
        for item in items
        if all(criterion(item, spec, current) for criterion in _CRITERIA)
    ]
