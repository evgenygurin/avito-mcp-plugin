"""Типобезопасные тулзы своего кабинета Avito (официальный API).

Поверх generic-клиента официального API дают structured output (Pydantic-модели)
для частых задач «мои объявления / мой аккаунт». Только СВОИ данные.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from ..models import AccountInfo, OwnItem, OwnItemsResult
from .official_api import build_client

# Ключи-контейнеры, под которыми официальный API отдаёт список ресурсов.
_LIST_KEYS = ("resources", "items", "result")


def _extract_list(raw: Any) -> list[dict[str, Any]]:
    """Достать список объявлений из ответа API, устойчиво к форме."""
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        for key in _LIST_KEYS:
            value = raw.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def _to_own_item(data: dict[str, Any]) -> OwnItem:
    """Мягко смаппить сырой объект объявления в OwnItem."""
    category = data.get("category")
    if isinstance(category, dict):
        category_name = category.get("name")
    elif isinstance(category, str):
        category_name = category
    else:
        category_name = None
    return OwnItem(
        id=data["id"],
        title=data.get("title"),
        status=data.get("status"),
        url=data.get("url"),
        price=data.get("price"),
        category=category_name,
    )


async def _fetch(ctx: Context, method: str, path: str) -> Any:
    """Вызвать официальный API, обернув ошибки в ToolError и закрыв клиент.

    Единая обработка для тулз своего кабинета: отсутствие кредов и запрет
    эндпоинта (ValueError), и HTTP-ошибки → ToolError с понятным текстом.
    """
    try:
        client = build_client()
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    try:
        await ctx.info(f"official API {method} {path}")
        return await client.call(method, path)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise ToolError(
            f"официальный API вернул HTTP {exc.response.status_code}"
        ) from exc
    finally:
        await client.aclose()


def register(mcp: FastMCP) -> None:
    """Зарегистрировать тулзы своего кабинета на инстансе FastMCP."""

    @mcp.tool
    async def get_own_items(ctx: Context) -> OwnItemsResult:
        """Вернуть список СВОИХ объявлений Avito (id, заголовок, статус, цена).

        Use when пользователь хочет посмотреть свои размещённые объявления.
        Требует AVITO_CLIENT_ID и AVITO_CLIENT_SECRET в окружении. Только свои
        данные (официальный API), не для сбора чужих объявлений.
        """
        raw = await _fetch(ctx, "GET", "core/v1/items")
        return OwnItemsResult(items=[_to_own_item(x) for x in _extract_list(raw)])

    @mcp.tool
    async def get_account_info(ctx: Context) -> AccountInfo:
        """Вернуть данные СВОЕГО аккаунта Avito: user_id и отображаемое имя.

        Use when нужен user_id (напр. для статистики) или проверка кабинета.
        Требует AVITO_CLIENT_ID и AVITO_CLIENT_SECRET. ПДн (email/phone) не
        возвращаются — минимизация. Только свой аккаунт.
        """
        raw = await _fetch(ctx, "GET", "core/v1/accounts/self")
        if (
            isinstance(raw, dict)
            and "id" not in raw
            and isinstance(raw.get("result"), dict)
        ):
            raw = raw["result"]
        return AccountInfo.model_validate(raw)
