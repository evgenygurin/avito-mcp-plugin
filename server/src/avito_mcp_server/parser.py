"""Ядро извлечения данных из HTML каталога Avito.

Avito отдаёт SSR-состояние в теге ``<script type="mime/invalid" data-mfe-state="true">``
(html-escaped JSON). Внутри — ``loaderData.data``: либо каталог (``catalog.items``),
либо состояние SSR-редиректа на канонический URL категории (``redirected``/``url``).
"""

from __future__ import annotations

import html as html_lib
import json
import logging
import time
from collections.abc import Callable
from typing import Any

from bs4 import BeautifulSoup

from .models import Listing

log = logging.getLogger(__name__)


def find_json_on_page(html_code: str) -> dict[str, Any]:
    """Найти встроенный SSR-JSON и вернуть ``loaderData.data`` (или ``{}``)."""
    soup = BeautifulSoup(html_code, "html.parser")
    for script in soup.select("script"):
        if (
            script.get("type") == "mime/invalid"
            and script.get("data-mfe-state") == "true"
            and "sandbox" not in script.text
        ):
            try:
                data = json.loads(html_lib.unescape(script.text))
            except (ValueError, TypeError):
                continue
            if isinstance(data, dict) and data.get("i18n", {}).get("hasMessages"):
                loader = data.get("loaderData", {})
                if isinstance(loader, dict) and isinstance(loader.get("data"), dict):
                    return loader["data"]
    return {}


# Маркеры страницы «Доступ ограничен: проблема с IP» (Qrator firewall + капча).
_FIREWALL_MARKERS = ("firewall-container", "js-firewall-form", "firewallCaptcha")

_STATUS_HINTS = {
    "firewall": (
        "Avito заблокировал IP (страница «проблема с IP» с капчей). Капчу не решаем: "
        "нужен чистый RU-прокси — задайте AVITO_PROXY и AVITO_PROXY_CHANGE_URL"
    ),
    "softblock": (
        "страница отдалась без каталога (поведенческий флаг) — обычно помогает "
        "смена IP или свежие куки"
    ),
    "nojson": "во встроенном состоянии страницы нет данных каталога",
    "redirect": "страница вернула SSR-редирект вместо каталога",
}


def next_page_url(catalog: dict[str, Any]) -> str | None:
    """Абсолютный URL следующей страницы каталога или ``None`` на последней.

    Каталог несёт готовый ``pager.next`` (относительный путь с ``context`` и ``p``),
    поэтому пагинация — обход этих ссылок, а не сборка параметров внутреннего API.
    """
    pager = catalog.get("pager")
    if not isinstance(pager, dict):
        return None
    nxt = pager.get("next")
    if not nxt:
        return None
    return f"https://www.avito.ru{nxt}" if str(nxt).startswith("/") else str(nxt)


def walk_pages(
    fetch: Callable[[Any, str], tuple[str, Any]],
    client: Any,
    url: str,
    pages: int,
    pause: float = 0.0,
) -> list[Listing]:
    """Обойти до ``pages`` страниц каталога, вернуть объявления без дублей.

    ``fetch`` передаётся аргументом (а не импортируется), чтобы тулзы подставляли
    свою ссылку — иначе моки сетевой границы в их тестах не сработают. Обход
    прекращается, когда каталог перестаёт отдавать ``pager.next``.
    """
    collected: list[Listing] = []
    seen: set[int] = set()
    page_url: str | None = url
    for index in range(max(1, pages)):
        if page_url is None:
            break
        if index and pause:
            time.sleep(pause)
        log.info("страница %s/%s: %s", index + 1, max(1, pages), page_url)
        kind, catalog = fetch(client, page_url)
        if kind != "ok":
            raise RuntimeError(explain_status(kind))
        # Каталог сдвигается между запросами — дедуп по id обязателен.
        for listing in extract_facts(catalog):
            if listing.id not in seen:
                seen.add(listing.id)
                collected.append(listing)
        log.info(
            "страница %s: всего накоплено %s объявлений", index + 1, len(collected)
        )
        page_url = next_page_url(catalog)
    return collected


def explain_status(kind: str) -> str:
    """Человекочитаемый диагноз для статуса ``classify`` — для сообщений тулз."""
    hint = _STATUS_HINTS.get(kind)
    return (
        f"{hint} (статус: {kind})"
        if hint
        else f"страница не отдала каталог (статус: {kind})"
    )


def classify(html_code: str) -> tuple[str, Any]:
    """Классифицировать страницу.

    Возвращает одно из:
    - ``("ok", catalog)`` — есть каталог с объявлениями;
    - ``("redirect", url)`` — SSR-редирект на канонический URL;
    - ``("firewall", None)`` — страница блокировки по IP с капчей;
    - ``("softblock", None)`` — 200, но каталога нет (поведенческий флаг/заглушка);
    - ``("nojson", None)`` — встроенного состояния не найдено.
    """
    data = find_json_on_page(html_code)
    if not data:
        if any(marker in html_code for marker in _FIREWALL_MARKERS):
            return "firewall", None
        return "nojson", None
    if data.get("redirected") and data.get("url"):
        return "redirect", data["url"]
    catalog = data.get("catalog")
    if isinstance(catalog, dict) and catalog.get("items"):
        return "ok", catalog
    return "softblock", None


# Значения больше этого порога — заведомо миллисекунды (в секундах это был бы
# 5138 год). Avito отдаёт sortTimeStamp в мс, но встречаются и секунды.
_MS_THRESHOLD = 100_000_000_000


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


_ITEM_KEYS = ("item", "itemFull", "listing")


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


def parse_listing_detail(html_code: str, with_views: bool = False) -> Listing | None:
    """Извлечь детальную информацию об одном объявлении из SSR-состояния страницы."""
    data = find_json_on_page(html_code)
    if not data:
        return None
    item = _find_item(data)
    if item is None:
        return None
    price_detailed = item.get("priceDetailed") or {}
    price = price_detailed.get("value") if isinstance(price_detailed, dict) else None
    url_path = item.get("urlPath")
    seller_id = item.get("sellerId")
    views = _extract_views(item) if with_views else None
    return Listing(
        id=item["id"],
        title=item.get("title") or "",
        price=price,
        address=_address(item),
        url=f"https://www.avito.ru{url_path}" if url_path else None,
        seller_id=str(seller_id) if seller_id else None,
        is_promotion=bool(item.get("isPromotion")),
        published_at=_published_at(item),
        params=_extract_params(item),
        views=views,
        description=item.get("description") or None,
    )


def extract_facts(catalog: dict[str, Any]) -> list[Listing]:
    """Смаппить ``catalog.items`` в ``Listing`` — только факты, без ПДн."""
    out: list[Listing] = []
    for item in catalog.get("items", []):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        price_detailed = item.get("priceDetailed") or {}
        price = (
            price_detailed.get("value") if isinstance(price_detailed, dict) else None
        )
        url_path = item.get("urlPath")
        seller_id = item.get("sellerId")
        out.append(
            Listing(
                id=item["id"],
                title=item.get("title") or "",
                price=price,
                address=_address(item),
                # urlPath уже начинается со "/" — склейка без лишнего слэша.
                url=f"https://www.avito.ru{url_path}" if url_path else None,
                seller_id=str(seller_id) if seller_id else None,
                is_promotion=bool(item.get("isPromotion")),
                published_at=_published_at(item),
            )
        )
    return out
