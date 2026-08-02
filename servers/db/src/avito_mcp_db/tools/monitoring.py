"""MCP-тулзы db-сервера: персистенция результатов скана и история цены.

db — единственный сервер со знанием о БД. Gateway/scraper отдают сырой
результат сканирования; dedup/seen/история цены пишутся здесь контрактом
``record_scan_result``.
"""

from __future__ import annotations

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from avito_mcp_scraper.models import (
    Listing,
    PriceHistoryResult,
    PricePoint,
    ScanItem,
    ScanResult,
)
from avito_mcp_scraper.tools.execution import run_blocking
from avito_mcp_scraper.utils import extract_listing_id

from ..config import build_storage
from ..storage import SeenRow


def _changes(listings: list[Listing], seen: dict[int, float | None]) -> list[ScanItem]:
    """Отобрать новые и подешевевшие объявления относительно снимка хранилища.

    Наличие id в ``seen`` = «видели раньше», значение = прошлая цена; без этого
    различия объявления без цены считались бы новыми при каждом скане.
    Чистая функция — сравнение проверяется без похода в базу.
    """
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
    return items


def _to_rows(listings: list[Listing]) -> list[SeenRow]:
    return [
        SeenRow(id=item.id, url=item.url, title=item.title, price=item.price)
        for item in listings
    ]


def register(mcp: FastMCP) -> None:
    """Зарегистрировать мониторинг-тулзы db (персист + история) на инстансе."""

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        # Аналог scan_new_listings в gateway — обход каталога идёт там; тут
        # только запись, но конвейер тоже сетевой (клиент-сторона).
        timeout=900,
    )
    async def record_scan_result(
        listings: list[Listing],
        ctx: Context,
    ) -> ScanResult:
        """Записать результат сканирования в хранилище и вернуть изменения.

        Use when результат ``scan_new_listings`` (сырой список объявлений,
        собранный gateway/scraper) нужно сверить с хранилищем и сохранить:
        dedup новых, фиксация снижения цены, история цены. Требует
        ``AVITO_SUPABASE_DSN``.

        Args:
            listings: список объявлений каталога (без фильтрации по новизне).
        """
        await ctx.info(f"record_scan_result: {len(listings)} listings")

        def _run() -> ScanResult:
            db = build_storage()
            # Одна выборка на всю страницу вместо запроса на объявление: база
            # облачная, и сотня round-trip'ов дороже самого парсинга.
            seen = db.fetch_seen([listing.id for listing in listings])
            items = _changes(listings, seen)
            db.upsert_seen_many(_to_rows(listings))
            return ScanResult(items=items)

        result = await run_blocking(
            _run,
            failure="не удалось записать результат сканирования",
            operation="record_scan_result",
            ctx=ctx,
        )

        await ctx.info(
            f"записано: {result.new_count} новых, {result.dropped_count} подешевевших"
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
        # extract_listing_id понимает и URL, и голые цифры — отдельной ветки
        # под каждый вид ввода не нужно.
        item_id = extract_listing_id(listing_id)
        await ctx.info(f"get_price_history: {item_id}")

        def _run() -> PriceHistoryResult:
            db = build_storage()
            rows = db.get_price_history(item_id)
            history = [
                PricePoint(price=price, seen_at=seen_at) for price, seen_at in rows
            ]
            return PriceHistoryResult(listing_id=item_id, history=history)

        return await run_blocking(
            _run,
            failure="не удалось получить историю цены",
            operation="get_price_history",
        )