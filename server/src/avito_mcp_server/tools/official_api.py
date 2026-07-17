"""MCP-тулза official_api_call — доступ к официальному API Avito."""

from __future__ import annotations

from typing import Any

import httpx
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from ..official_api import AvitoOfficialClient, AvitoOfficialConfig


def build_client() -> AvitoOfficialClient:
    """Собрать клиент официального API из окружения (AVITO_CLIENT_ID/SECRET)."""
    config = AvitoOfficialConfig.from_env()
    return AvitoOfficialClient(config, httpx.AsyncClient())


def register(mcp: FastMCP) -> None:
    """Зарегистрировать тулзы официального API на инстансе FastMCP."""

    @mcp.tool
    async def official_api_call(
        method: str,
        path: str,
        ctx: Context,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Вызвать метод официального API Avito (api.avito.ru) для СВОИХ объявлений.

        Use when пользователь управляет своими объявлениями, рекламой или
        статистикой. Требует AVITO_CLIENT_ID и AVITO_CLIENT_SECRET в окружении.
        НЕ для сбора чужих объявлений. Параметры: method — HTTP-метод (GET/POST),
        path — путь API (напр. "core/v1/items"), params — query-параметры.
        """
        try:
            client = build_client()
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

        try:
            await ctx.info(f"official API {method} {path}")
            return await client.call(method, path, params)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            raise ToolError(
                f"официальный API вернул HTTP {exc.response.status_code}"
            ) from exc
        finally:
            await client.aclose()
