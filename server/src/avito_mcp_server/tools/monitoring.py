"""MCP-тулзы мониторинга: scan_new_listings (dedup + цена) + get_price_history."""

from __future__ import annotations

import asyncio

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from ..config import build_http_client, build_storage, page_pause
from ..filters.filters import FilterSpec, apply_filters
from ..http.client import fetch_catalog
from ..models import PriceHistoryResult, PricePoint, ScanItem, ScanResult
from ..parser import walk_pages
from ..utils import extract_listing_id


def register(mcp: FastMCP) -> None:
    """Зарегистрировать тулзы мониторинга на инстансе FastMCP."""

    @mcp.tool
    async def scan_new_listings(
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
    ) -> ScanResult:
        """Собрать новые и подешевевшие объявления (мониторинг-примитив).

        Use when нужно отследить новые объявления или снижение цены по регулярному
        поиску (вызывается внешним планировщиком — агентом/cron). Сверяет свежий
        каталог с хранилищем в Postgres (``AVITO_SUPABASE_DSN``). Фильтры — те же, что в
        search_listings, включая ``pages`` (сколько страниц каталога обойти).
        Возвращает только новые объявления и те, что подешевели;
        неизменившиеся пропускает. Требует ``AVITO_SUPABASE_DSN``.
        """
        spec = FilterSpec(
            include_keywords=include_keywords or [],
            exclude_keywords=exclude_keywords or [],
            seller_blacklist=seller_blacklist or [],
            price_min=price_min,
            price_max=price_max,
            geo=geo,
            max_age=max_age,
        )
        await ctx.info(f"scan_new_listings: {url}")

        def _run() -> ScanResult:
            client = build_http_client()
            db = build_storage()
            found = walk_pages(fetch_catalog, client, url, pages, pause=page_pause())
            listings = apply_filters(found, spec)

            items: list[ScanItem] = []
            for listing in listings:
                prev_price = db.get_previous_price(listing.id)
                # Новизну определяет сам upsert: `prev_price is None` означало бы
                # «новое» и для объявлений без цены — они попадали в выдачу при
                # каждом скане.
                is_new = db.upsert_seen(
                    listing.id,
                    listing.url,
                    listing.title,
                    listing.price,
                )
                if is_new:
                    items.append(ScanItem(listing=listing, is_new=True))
                elif (
                    prev_price is not None
                    and listing.price is not None
                    and listing.price < prev_price
                ):
                    items.append(
                        ScanItem(
                            listing=listing,
                            is_new=False,
                            price_delta=prev_price - listing.price,
                        )
                    )
            return ScanResult(items=items)

        try:
            result = await asyncio.to_thread(_run)
        except Exception as exc:
            raise ToolError(f"не удалось выполнить сканирование: {exc}") from exc

        await ctx.info(
            f"найдено {result.new_count} новых, {result.dropped_count} подешевевших"
        )
        return result

    @mcp.tool
    async def get_price_history(
        listing_id: str,
        ctx: Context,
    ) -> PriceHistoryResult:
        """Получить историю цены объявления из хранилища.

        Use when нужна динамика цены конкретного объявления (было/стало).
        Принимает числовой id объявления Avito или его URL. Возвращает
        хронологию цены отсортированную от свежей к старой. История
        появляется только после того, как объявление попадало в
        ``scan_new_listings``. Требует ``AVITO_SUPABASE_DSN``.
        """
        if listing_id.startswith(("http://", "https://")):
            item_id = extract_listing_id(listing_id)
        else:
            try:
                item_id = int(listing_id)
            except ValueError:
                item_id = extract_listing_id(listing_id)

        await ctx.info(f"get_price_history: {item_id}")

        def _run() -> PriceHistoryResult:
            db = build_storage()
            rows = db.get_price_history(item_id)
            history = [
                PricePoint(price=price, seen_at=seen_at) for price, seen_at in rows
            ]
            return PriceHistoryResult(listing_id=item_id, history=history)

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:
            raise ToolError(f"не удалось получить историю цены: {exc}") from exc
