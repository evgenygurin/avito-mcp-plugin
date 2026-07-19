"""MCP-тулзы мониторинга: scan_new_listings (dedup + цена) + get_price_history."""

from __future__ import annotations

import asyncio

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from ..config import build_http_client, build_storage, page_pause
from ..filters.filters import FilterSpec, PageCount, apply_filters
from ..http.client import fetch_catalog
from ..models import PriceHistoryResult, PricePoint, ScanItem, ScanResult
from ..parser import walk_pages
from ..storage.supabase import SeenRow
from ..utils import extract_listing_id


def register(mcp: FastMCP) -> None:
    """Зарегистрировать тулзы мониторинга на инстансе FastMCP."""

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
    )
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
        pages: PageCount = 1,
    ) -> ScanResult:
        """Собрать новые и подешевевшие объявления (мониторинг-примитив).

        Use when нужно отследить новые объявления или снижение цены по регулярному
        поиску (вызывается внешним планировщиком — агентом/cron). Сверяет свежий
        каталог с хранилищем в Postgres (``AVITO_SUPABASE_DSN``). Возвращает
        только новые объявления и те, что подешевели; неизменившиеся пропускает.
        Требует ``AVITO_SUPABASE_DSN``.

        Args:
            url: ссылка на каталог Avito (категория/город).
            include_keywords: оставить только объявления с одним из этих слов
                в заголовке (регистр не важен).
            exclude_keywords: отбросить объявления с любым из этих слов в
                заголовке.
            seller_blacklist: отбросить объявления этих продавцов (seller_id).
            price_min: минимальная цена включительно.
            price_max: максимальная цена включительно.
            geo: подстрока адреса объявления (район, улица).
            max_age: максимальный возраст объявления в СЕКУНДАХ с момента
                публикации (не дни и не unix-timestamp).
            pages: сколько страниц каталога обойти; обход прекращается на
                последней странице сам.
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
        await ctx.info(f"scan_new_listings: {url}")

        def _run() -> ScanResult:
            client = build_http_client()
            db = build_storage()
            found = walk_pages(fetch_catalog, client, url, pages, pause=page_pause())
            listings = apply_filters(found, spec)

            # Одна выборка на страницу вместо запроса на объявление: база
            # облачная, и раньше сотня round-trip'ов занимала больше времени,
            # чем сам парсинг. Наличие id в `seen` = «видели раньше», значение =
            # прошлая цена; без этого различия объявления без цены считались
            # новыми при каждом скане.
            seen = db.fetch_seen([listing.id for listing in listings])

            items: list[ScanItem] = []
            for listing in listings:
                if listing.id not in seen:
                    items.append(ScanItem(listing=listing, is_new=True))
                    continue
                prev_price = seen[listing.id]
                if (
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

            db.upsert_seen_many(
                [
                    SeenRow(
                        id=listing.id,
                        url=listing.url,
                        title=listing.title,
                        price=listing.price,
                    )
                    for listing in listings
                ]
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

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True, idempotentHint=True, openWorldHint=False
        ),
    )
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
