"""Ядро извлечения данных из HTML каталога Avito.

Avito отдаёт SSR-состояние в теге ``<script type="mime/invalid" data-mfe-state="true">``
(html-escaped JSON). Внутри — ``loaderData.data``: либо каталог (``catalog.items``),
либо состояние SSR-редиректа на канонический URL категории (``redirected``/``url``).
"""

from __future__ import annotations

import html as html_lib
import json
from typing import Any

from bs4 import BeautifulSoup

from .models import Listing


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


def classify(html_code: str) -> tuple[str, Any]:
    """Классифицировать страницу.

    Возвращает одно из:
    - ``("ok", catalog)`` — есть каталог с объявлениями;
    - ``("redirect", url)`` — SSR-редирект на канонический URL;
    - ``("softblock", None)`` — 200, но каталога нет (поведенческий флаг/заглушка);
    - ``("nojson", None)`` — встроенного состояния не найдено.
    """
    data = find_json_on_page(html_code)
    if not data:
        return "nojson", None
    if data.get("redirected") and data.get("url"):
        return "redirect", data["url"]
    catalog = data.get("catalog")
    if isinstance(catalog, dict) and catalog.get("items"):
        return "ok", catalog
    return "softblock", None


def _address(item: dict[str, Any]) -> str | None:
    addr = item.get("addressDetailed") or {}
    loc = item.get("location") or {}
    geo = item.get("geo") or {}
    return (
        (addr.get("locationName") if isinstance(addr, dict) else None)
        or (loc.get("name") if isinstance(loc, dict) else None)
        or (geo.get("formattedAddress") if isinstance(geo, dict) else None)
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
                published_at=item.get("sortTimeStamp"),
            )
        )
    return out
