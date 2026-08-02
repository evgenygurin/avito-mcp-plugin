"""MCP-тулзы db-сервера: персистент результата сканирования и история цены.

db — единственный сервер со знанием о БД. Gateway/scraper отдают сырой
результат сканирования; dedup/seen/история цены пишутся здесь контрактом
``record_scan_result``. Чистые функции (``persist_scan``, ``fetch_history``)
вынесены в модуль, чтобы gateway мог звать персистент без IPC-оверхеда
(импортом), оставляя тулзы тонкой обёрткой для внешних MCP-клиентов.
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


def persist_scan(listings: list[Listing]) -> ScanResult:
    """Записать результат сканирования и вернуть изменения (dedup + цена).

    Чистая функция поверх хранилища: gateway зовёт её из ``scan_new_listings``
    импортом. Одна выборка на всю пачку вместо запроса на объявление: база
    облачная, и сотня round-trip'ов дороже самого парсинга.
    """
    db = build_storage()
    seen = db.fetch_seen([listing.id for listing in listings])
    items = _changes(listings, seen)
    db.upsert_seen_many(_to_rows(listings))
    return ScanResult(items=items)


def fetch_history(listing_id: str) -> PriceHistoryResult:
    """История цены объявления (свежая первой). Чистая функция от хранилища."""
    item_id = extract_listing_id(listing_id)
    db = build_storage()
    rows = db.get_price_history(item_id)
    history = [PricePoint(price=price, seen_at=seen_at) for price, seen_at in rows]
    return PriceHistoryResult(listing_id=item_id, history=history)


def register_record(mcp: FastMCP) -> None:
    """Зарегистрировать ``record_scan_result`` (внутренний контракт персистента)."""

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        timeout=900,
    )
    async def record_scan_result(
        listings: list[Listing],
        ctx: Context,
    ) -> ScanResult:
        """Сырой результат сканирования → записать dedup/seen/историю цены.

        Внутренний контракт: gateway собирает каталог через scraper и отдаёт
        сырой список объявлений сюда; db пишет его и возвращает, что изменилось.
        Требует ``AVITO_SUPABASE_DSN``.

        Args:
            listings: список объявлений каталога (без фильтрации по новизне).
        """
        await ctx.info(f"record_scan_result: {len(listings)} listings")

        result = await run_blocking(
            lambda: persist_scan(listings),
            failure="не удалось записать результат сканирования",
            operation="record_scan_result",
            ctx=ctx,
        )
        await ctx.info(
            f"записано: {result.new_count} новых, {result.dropped_count} подешевевших"
        )
        return result


def register_history(mcp: FastMCP) -> None:
    """Зарегистрировать ``get_price_history`` (внешний контракт, в т.ч. в gateway)."""

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

        Принимает числовой id объявления Avito или его URL. Возвращает
        хронологию цены от свежей к старой. История появляется после того, как
        объявление попадало в ``scan_new_listings``. Требует ``AVITO_SUPABASE_DSN``.
        """
        item_id = extract_listing_id(listing_id)
        await ctx.info(f"get_price_history: {item_id}")

        return await run_blocking(
            lambda: fetch_history(listing_id),
            failure="не удалось получить историю цены",
            operation="get_price_history",
        )


# Псевдоним для обратной совместимости регистрации обоих мониторинг-тулз.
def register(mcp: FastMCP) -> None:
    """Зарегистрировать мониторинг-тулз db: запись и историю."""
    register_record(mcp)
    register_history(mcp)
