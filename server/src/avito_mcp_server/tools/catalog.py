"""Общий блокирующий пайплайн обхода каталога для тулз поиска и мониторинга.

``search_listings`` и ``scan_new_listings`` расходятся только тем, что делают
с готовым списком: первая отдаёт его как есть, вторая сверяет с хранилищем.
Сам сбор — клиент → обход страниц → фильтры — один и тот же, и живёт здесь.

Это и единственная граница мока сетевого слоя для обеих тулз: подменяется
``catalog.fetch_catalog`` (см. tests/test_tools_search.py).
"""

from __future__ import annotations

from ..config import build_http_client, page_pause
from ..filters.filters import FilterSpec, apply_filters
from ..http.client import fetch_catalog
from ..models import Listing
from ..parser import walk_pages


def collect_listings(url: str, spec: FilterSpec, pages: int) -> list[Listing]:
    """Обойти каталог и вернуть объявления, прошедшие фильтры.

    Блокирующая функция: вызывается из потока (см. ``tools.execution``).
    """
    client = build_http_client()
    found = walk_pages(fetch_catalog, client, url, pages, pause=page_pause())
    return apply_filters(found, spec)
