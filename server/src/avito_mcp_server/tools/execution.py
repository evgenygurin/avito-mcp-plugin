"""Общая граница выполнения MCP-тулз: поток + единый контракт ошибок.

Движок парсинга синхронный и блокирующий (curl_cffi, psycopg), поэтому каждая
тулза уводит работу в поток и приводит любой сбой к ``ToolError``. Раньше эта
пара `asyncio.to_thread` + `try/except` была скопирована в каждую из 7 тулз —
здесь она описана один раз.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from fastmcp.exceptions import ToolError

log = logging.getLogger(__name__)


async def run_blocking[T](action: Callable[[], T], *, failure: str) -> T:
    """Выполнить блокирующее ``action`` в потоке; сбой — ``ToolError``.

    Args:
        action: синхронная работа тулзы (сеть, БД, файлы).
        failure: префикс сообщения об ошибке — что именно не удалось.

    Тулзы обязаны логировать через ``ctx`` (это async), поэтому сама тулза
    остаётся ``async def``, а в поток уходит только блокирующее ядро.
    ``ToolError`` из ``action`` пробрасывается как есть — он уже несёт
    сформулированный наружу диагноз и не нуждается в повторной обёртке.
    """
    try:
        return await asyncio.to_thread(action)
    except ToolError:
        raise
    except Exception as exc:
        # Трейсбек остаётся в логе сервера: ToolError клиент видит как
        # сформулированный отказ, а не как сбой, который стоит расследовать.
        log.exception("%s", failure)
        # У таймаутов httpx/asyncio str(exc) пустой — без подстановки типа
        # пользователь получал бы «не удалось получить объявления: » без причины.
        detail = str(exc) or type(exc).__name__
        raise ToolError(f"{failure}: {detail}") from exc
