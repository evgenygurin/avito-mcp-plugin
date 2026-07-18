"""MCP-тулза диагностики прокси/кук."""

from __future__ import annotations

import asyncio
import os

from fastmcp import Context, FastMCP

from ..config import build_http_client
from ..http.client import fetch_catalog
from ..models import ProxyHealth

_PROBE_URL = "https://www.avito.ru/nizhniy_novgorod/kvartiry/prodam"


def register(mcp: FastMCP) -> None:
    """Зарегистрировать диагностическую тулзу на инстансе FastMCP."""

    @mcp.tool
    async def check_proxy_health(
        ctx: Context,
        probe_url: str = _PROBE_URL,
    ) -> ProxyHealth:
        """Проверить связку прокси+кук: пробует получить каталог, сообщает исход.

        Use when надо убедиться, что антибот пробивается (прокси/куки рабочие),
        до массового парсинга. Возвращает конфиг и результат пробного запроса; при
        блокировке НЕ бросает ошибку — это валидный диагноз (``ok=false``).
        """
        provider = os.getenv("AVITO_COOKIE_PROVIDER", "spfa")
        await ctx.info(f"check_proxy_health: {probe_url}")

        def _run() -> ProxyHealth:
            client = build_http_client()
            proxy_type = type(client.proxy).__name__
            try:
                kind, _ = fetch_catalog(client, probe_url)
                ok = kind == "ok"
                detail = "каталог получен" if ok else f"страница вернула: {kind}"
            except Exception as exc:  # noqa: BLE001
                ok = False
                detail = f"ошибка: {exc}"
            return ProxyHealth(
                ok=ok,
                cookie_provider=provider,
                proxy_type=proxy_type,
                detail=detail,
            )

        return await asyncio.to_thread(_run)
