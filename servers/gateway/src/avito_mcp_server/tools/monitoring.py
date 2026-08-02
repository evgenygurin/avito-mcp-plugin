"""Gateway-тулзы мониторинга: scan_new_listings + история цены (делегация в db).

Gateway не знает про БД: собирает каталог через scraper-движок и отдаёт
результат на персистент в db (``persist_scan`` находится в db). Тулуна
``get_price_history`` gateway тоже регистрирует из db (внешний контракт).
"""

from __future__ import annotations

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from avito_mcp_scraper.filters.filters import FilterSpec, PageCount
from avito_mcp_scraper.models import ScanResult
from avito_mcp_scraper.tools.catalog import collect_listings
from avito_mcp_scraper.tools.execution import run_blocking

from avito_mcp_db.tools.monitoring import persist_scan


def register(mcp: FastMCP) -> None:
    """Зарегистрировать gateway-тулзу ``scan_new_listings`` на инстансе."""

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        # См. аналогичный комментарий в tools/search.py — тот же движок обхода.
        timeout=900,
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
        поиску (вызывается внешним планировщиком — агентом/cron). Собирает свежий
        каталог (scraper) и отдаёт его на персистент в db (Postgres-хранилище),
        где сверяются dedup и история цены. Возвращает только новые объявления
        и те, что подешевели; неизменившиеся пропускает.

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
            # Память о выжженных прокси между запусками (cooldown_store) — Фаза 2
            # задокументировала отклонение переходного периода: scraper stateless,
            # а своё хранилище gateway больше не держит (оно ушло в db). Вернётся
            # с авто-фиксом Фазы 4, когда gateway будет звать db и cooldown.
            listings = collect_listings(url, spec, pages)
            return persist_scan(listings)

        result = await run_blocking(
            _run,
            failure="не удалось выполнить сканирование",
            operation="scan_new_listings",
            ctx=ctx,
        )

        await ctx.info(
            f"найдено {result.new_count} новых, {result.dropped_count} подешевевших"
        )
        return result
