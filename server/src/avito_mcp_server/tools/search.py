"""MCP-тулза поиска публичных объявлений Avito по каталогу."""

from __future__ import annotations

import asyncio

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from ..config import build_http_client, page_pause
from ..filters.filters import FilterSpec, apply_filters
from ..http.client import fetch_catalog
from ..models import Listing, SearchResult
from ..parser import walk_pages


def register(mcp: FastMCP) -> None:
    """Зарегистрировать тулзу поиска на инстансе FastMCP."""

    @mcp.tool
    async def search_listings(
        url: str,
        ctx: Context,
        include_keywords: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
        seller_blacklist: list[str] | None = None,
        price_min: float | None = None,
        price_max: float | None = None,
        geo: str | None = None,
        max_age: int | None = None,
        pages: int = 1,
    ) -> SearchResult:
        """Собрать публичные объявления Avito по ссылке на каталог.

        Use when пользователь хочет найти/сравнить объявления по ссылке на каталог
        Avito (напр. категория недвижимости города). Возвращает фактические поля
        (заголовок, цена, адрес, url) — БЕЗ ПДн продавцов.
        ``pages`` — сколько страниц каталога обойти (по умолчанию 1, ~50 объявлений
        на страницу); обход прекращается на последней странице сам.
        Опциональные фильтры: include/exclude ключевые слова (по заголовку),
        seller_blacklist, price_min/max, geo (подстрока адреса), max_age (секунды).
        Требует настроенных прокси/кук — см. .env.example.
        """
        spec = FilterSpec.from_optional(
            include_keywords=include_keywords,
            exclude_keywords=exclude_keywords,
            seller_blacklist=seller_blacklist,
            price_min=price_min,
            price_max=price_max,
            geo=geo,
            max_age=max_age,
        )
        await ctx.info(f"search_listings: {url}")

        def _run() -> list[Listing]:
            client = build_http_client()
            found = walk_pages(fetch_catalog, client, url, pages, pause=page_pause())
            return apply_filters(found, spec)

        try:
            items = await asyncio.to_thread(_run)
        except Exception as exc:
            raise ToolError(f"не удалось получить объявления: {exc}") from exc

        await ctx.info(f"найдено {len(items)} объявлений")
        return SearchResult(items=items)
