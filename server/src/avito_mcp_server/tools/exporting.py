"""MCP-тулза экспорта объявлений в xlsx/json/csv."""

from __future__ import annotations

import asyncio

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from ..export.exporter import export_listings as do_export
from ..models import ExportResult, Listing


def register(mcp: FastMCP) -> None:
    """Зарегистрировать тулзу экспорта на инстансе FastMCP."""

    @mcp.tool
    async def export_listings(
        items: list[dict[str, object]],
        ctx: Context,
        fmt: str = "xlsx",
        path: str | None = None,
    ) -> ExportResult:
        """Экспортировать объявления в xlsx/json/csv.

        Use when нужно сохранить результаты поиска в файл (Excel, JSON, CSV)
        для анализа или передачи. Принимает список объявлений (из
        search_listings), формат и опциональный путь. Без пути возвращает
        содержимое как строку (base64 для xlsx).
        """
        await ctx.info(f"export_listings: fmt={fmt}, count={len(items)}")

        def _run() -> ExportResult:
            parsed = [Listing.model_validate(item) for item in items]
            content, written_path = do_export(parsed, fmt, path)
            return ExportResult(
                format=fmt,
                path=written_path,
                content=content if not written_path else None,
                count=len(parsed),
            )

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:
            raise ToolError(f"не удалось экспортировать: {exc}") from exc
