"""MCP-тулза получения детальной информации об объявлении Avito."""

from __future__ import annotations

import asyncio

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from ..config import build_http_client
from ..models import Listing
from ..parser import parse_listing_detail
from ..utils import extract_listing_id


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
        if id_or_url.startswith(("http://", "https://")):
            url = id_or_url
        else:
            listing_id = extract_listing_id(id_or_url)
            url = f"https://www.avito.ru/items/{listing_id}"

        await ctx.info(f"get_listing: {url}")

        def _run() -> Listing:
            client = build_http_client()
            resp = client.get(url)
            listing = parse_listing_detail(resp.text, with_views=with_views)
            if listing is None:
                raise RuntimeError("не удалось извлечь данные объявления из страницы")
            return listing

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:
            raise ToolError(f"не удалось получить объявление: {exc}") from exc
