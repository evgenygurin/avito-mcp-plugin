"""Маппинг сырых объектов Avito в доменную модель ``Listing``.

Только факты: телефоны/имена продавцов сюда не переносятся (ПДн вне области
плагина). Формы записи у карточки каталога и детальной страницы разные, общее
подмножество полей собирает ``_common_fields``.
"""

from __future__ import annotations

from typing import Any

from ..models import Listing
from ..utils import to_absolute_avito_url
from .state import find_json_on_page

# Значения больше этого порога — заведомо миллисекунды (в секундах это был бы
# 5138 год). Avito отдаёт sortTimeStamp в мс, но встречаются и секунды.
_MS_THRESHOLD = 100_000_000_000

_ITEM_KEYS = ("item", "itemFull", "listing")


def _published_at(item: dict[str, Any]) -> int | None:
    """Время публикации в epoch-СЕКУНДАХ — единая единица для моделей и фильтров."""
    raw = item.get("sortTimeStamp")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value // 1000 if value > _MS_THRESHOLD else value


def _address(item: dict[str, Any]) -> str | None:
    """Собрать адрес: улица с домом + ориентиры (метро, район).

    Улица лежит в ``geo.formattedAddress``, район/метро — в ``geo.geoReferences``;
    ``locationName`` даёт лишь город, по нему нельзя отфильтровать район.
    """
    addr = item.get("addressDetailed") or {}
    loc = item.get("location") or {}
    geo = item.get("geo") or {}
    if not isinstance(geo, dict):
        geo = {}

    parts: list[str] = []
    street = geo.get("formattedAddress")
    if street:
        parts.append(str(street))
    for ref in geo.get("geoReferences") or []:
        content = ref.get("content") if isinstance(ref, dict) else None
        if content:
            parts.append(str(content))
    if parts:
        return ", ".join(parts)

    return (addr.get("locationName") if isinstance(addr, dict) else None) or (
        loc.get("name") if isinstance(loc, dict) else None
    )


def _find_item(data: dict[str, Any]) -> dict[str, Any] | None:
    for key in _ITEM_KEYS:
        candidate = data.get(key)
        if isinstance(candidate, dict) and candidate.get("id"):
            return candidate
    return None


def _extract_params(item: dict[str, Any]) -> dict[str, str]:
    params: dict[str, str] = {}
    raw = item.get("params") or item.get("parameters") or []
    if not isinstance(raw, list):
        return params
    for p in raw:
        if not isinstance(p, dict):
            continue
        name = p.get("name") or p.get("title") or ""
        value = p.get("value") or ""
        if name and value:
            params[name] = str(value)
    return params


def _extract_views(item: dict[str, Any]) -> int | None:
    stats = item.get("statistics")
    if isinstance(stats, dict):
        raw = stats.get("totalViews") or stats.get("views")
        if isinstance(raw, (int, float)):
            return int(raw)
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
    return None


def _price(item: dict[str, Any]) -> float | None:
    price_detailed = item.get("priceDetailed") or {}
    return price_detailed.get("value") if isinstance(price_detailed, dict) else None


def _seller_id(item: dict[str, Any]) -> str | None:
    seller_id = item.get("sellerId")
    return str(seller_id) if seller_id else None


def _listing_url(item: dict[str, Any]) -> str | None:
    # urlPath уже начинается со "/" — to_absolute_avito_url клеит без лишнего слэша.
    url_path = item.get("urlPath")
    return to_absolute_avito_url(str(url_path)) if url_path else None


def _common_fields(item: dict[str, Any]) -> dict[str, Any]:
    """Поля, общие для карточки каталога и детальной страницы объявления."""
    return {
        "id": item["id"],
        "title": item.get("title") or "",
        "price": _price(item),
        "address": _address(item),
        "url": _listing_url(item),
        "seller_id": _seller_id(item),
        "is_promotion": bool(item.get("isPromotion")),
        "published_at": _published_at(item),
    }


def parse_listing_detail(html_code: str, with_views: bool = False) -> Listing | None:
    """Извлечь детальную информацию об одном объявлении из SSR-состояния страницы."""
    data = find_json_on_page(html_code)
    if not data:
        return None
    item = _find_item(data)
    if item is None:
        return None
    return Listing(
        **_common_fields(item),
        params=_extract_params(item),
        views=_extract_views(item) if with_views else None,
        description=item.get("description") or None,
    )


def extract_facts(catalog: dict[str, Any]) -> list[Listing]:
    """Смаппить ``catalog.items`` в ``Listing`` — только факты, без ПДн."""
    return [
        Listing(**_common_fields(item))
        for item in catalog.get("items", [])
        if isinstance(item, dict) and item.get("id")
    ]
