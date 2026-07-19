"""Обход страниц каталога: ссылка на следующую страницу + сбор без дублей."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from ..models import Listing
from ..utils import to_absolute_avito_url
from .mapping import extract_facts
from .state import PageKind, PageResult, explain_status

log = logging.getLogger(__name__)

#: Как страница добывается: ``(client, url) -> (вид страницы, нагрузка)``.
#: Передаётся аргументом, а не импортируется, чтобы вызывающий (и тесты) могли
#: подменить сетевой слой — см. ``tools/catalog.py``.
FetchPage = Callable[[Any, str], PageResult]


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
    return to_absolute_avito_url(str(nxt))


def walk_pages(
    fetch: FetchPage,
    client: Any,
    url: str,
    pages: int,
    pause: float = 0.0,
) -> list[Listing]:
    """Обойти до ``pages`` страниц каталога, вернуть объявления без дублей.

    Обход прекращается, когда каталог перестаёт отдавать ``pager.next``.

    Raises:
        RuntimeError: страница вернула не каталог (блокировка, редирект-петля).
    """
    total = max(1, pages)
    collected: list[Listing] = []
    seen: set[int] = set()
    page_url: str | None = url
    for index in range(total):
        if page_url is None:
            break
        if index and pause:
            time.sleep(pause)
        log.info("страница %s/%s: %s", index + 1, total, page_url)
        kind, catalog = fetch(client, page_url)
        if kind != PageKind.OK:
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
