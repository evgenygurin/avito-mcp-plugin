"""MCP-тулза экспорта объявлений в xlsx/json/csv."""

from __future__ import annotations

import asyncio
from typing import Literal

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from ..export.exporter import export_listings as do_export
from ..models import ExportResult, Listing

ExportFormat = Literal["xlsx", "json", "csv"]


def register(mcp: FastMCP) -> None:
    """Зарегистрировать тулзу экспорта на инстансе FastMCP."""

    @mcp.tool(
        annotations=ToolAnnotations(destructiveHint=True, openWorldHint=False),
    )
    async def export_listings(
        items: list[Listing],
        ctx: Context,
        fmt: ExportFormat = "xlsx",
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
            content, written_path = do_export(items, fmt, path)
            return ExportResult(
                format=fmt,
                path=written_path,
                content=content if not written_path else None,
                count=len(items),
            )

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:
            raise ToolError(f"не удалось экспортировать: {exc}") from exc
