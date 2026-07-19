"""Ядро извлечения данных из HTML каталога Avito.

Пакет разбит по ответственностям, но остаётся единой точкой импорта — код и
тесты по-прежнему пишут ``from avito_mcp_server.parser import classify``:

- :mod:`.state` — встроенное SSR-состояние: поиск JSON и классификация страницы;
- :mod:`.mapping` — сырые объекты Avito → доменная модель ``Listing``;
- :mod:`.pagination` — обход страниц каталога и дедуп.
"""

from .mapping import extract_facts, parse_listing_detail
from .pagination import FetchPage, next_page_url, walk_pages
from .state import PageKind, PageResult, classify, explain_status, find_json_on_page

__all__ = [
    "FetchPage",
    "PageKind",
    "PageResult",
    "classify",
    "explain_status",
    "extract_facts",
    "find_json_on_page",
    "next_page_url",
    "parse_listing_detail",
    "walk_pages",
]
