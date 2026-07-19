"""MCP-тулза получения детальной информации об объявлении Avito."""

from __future__ import annotations

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from ..config import build_http_client
from ..models import Listing
from ..parser import parse_listing_detail
from ..utils import to_listing_url
from .execution import run_blocking


def register(mcp: FastMCP) -> None:
    """Зарегистрировать тулзу деталей объявления на инстансе FastMCP."""

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        # Один HTTP-запрос, но с тем же rotate-until-clean — тот же worst case
        # ~900с, что и у search_listings/scan_new_listings (см. комментарий там).
        timeout=900,
    )
    async def get_listing(
        id_or_url: str,
        ctx: Context,
        with_views: bool = False,
    ) -> Listing:
        """Получить детальную информацию об объявлении Avito.

        Use when пользователю нужны все детали конкретного объявления: цена,
        адрес, описание, параметры, просмотры. Принимает URL объявления или
        числовой id (напр. ``https://www.avito.ru/.../slug_1234567890`` или
        ``1234567890``). Для id без URL строит ``https://www.avito.ru/items/<id>``.
        ``with_views`` добавляет поле просмотров (отдельный запрос на Avito).
        Требует настроенных прокси/кук — см. .env.example.
        """
        url = to_listing_url(id_or_url)
        await ctx.info(f"get_listing: {url}")

        def _run() -> Listing:
            client = build_http_client()
            resp = client.get(url)
            listing = parse_listing_detail(resp.text, with_views=with_views)
            if listing is None:
                raise RuntimeError("не удалось извлечь данные объявления из страницы")
            return listing

        return await run_blocking(_run, failure="не удалось получить объявление")
