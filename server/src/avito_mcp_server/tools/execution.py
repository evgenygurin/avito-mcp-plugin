"""Общая граница выполнения MCP-тулз: поток + единый контракт ошибок.

Движок парсинга синхронный и блокирующий (curl_cffi, psycopg), поэтому каждая
тулза уводит работу в поток и приводит любой сбой к ``ToolError``. Раньше эта
пара `asyncio.to_thread` + `try/except` была скопирована в каждую из 7 тулз —
здесь она описана один раз.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Iterator
from typing import Any, Protocol

from fastmcp.exceptions import ToolError

from ..progress import sink
from ..timing import Timings, track

log = logging.getLogger(__name__)


class ProgressReporter(Protocol):
    """Та часть ``fastmcp.Context``, что нужна для отчёта о прогрессе."""

    async def report_progress(
        self,
        progress: float,
        total: float | None = None,
        message: str | None = None,
    ) -> None: ...


@contextlib.contextmanager
def _progress_bridge(ctx: ProgressReporter | None) -> Iterator[None]:
    """Пробросить прогресс из рабочего потока на петлю событий.

    ``report_progress`` — корутина, а движок парсинга живёт в потоке, где
    ``await`` невозможен: отправляем корутину на петлю через
    ``run_coroutine_threadsafe`` и НЕ ждём результата. Ждать нельзя — поток
    парсинга блокировался бы на каждой странице ради вспомогательного канала.

    Сбой отчёта проглатывается: клиент, не поддерживающий прогресс, не повод
    терять уже собранные объявления.
    """
    if ctx is None:
        yield
        return

    loop = asyncio.get_running_loop()

    def _send(current: float, total: float | None, message: str | None) -> None:
        try:
            future = asyncio.run_coroutine_threadsafe(
                ctx.report_progress(current, total, message), loop
            )
        except Exception as exc:  # noqa: BLE001 — прогресс не критичен
            log.debug("не удалось отправить прогресс: %s", exc)
            return
        future.add_done_callback(_swallow)

    def _swallow(future: Any) -> None:
        # Исключение внутри корутины иначе всплывёт как "never retrieved".
        with contextlib.suppress(Exception):
            future.result()

    with sink(_send):
        yield


async def run_blocking[T](
    action: Callable[[], T],
    *,
    failure: str,
    operation: str | None = None,
    ctx: ProgressReporter | None = None,
) -> T:
    """Выполнить блокирующее ``action`` в потоке; сбой — ``ToolError``.

    Args:
        action: синхронная работа тулзы (сеть, БД, файлы).
        failure: префикс сообщения об ошибке — что именно не удалось.
        operation: метка для сводной строки замеров (обычно имя тулзы);
            по умолчанию — текст ``failure``.
        ctx: контекст тулзы — с ним движок сможет отчитываться о прогрессе
            (``progress.report``), без него отчёты просто игнорируются.

    Тулзы обязаны логировать через ``ctx`` (это async), поэтому сама тулза
    остаётся ``async def``, а в поток уходит только блокирующее ядро.
    ``ToolError`` из ``action`` пробрасывается как есть — он уже несёт
    сформулированный наружу диагноз и не нуждается в повторной обёртке.

    Здесь же заводится копилка замеров на вызов: ``asyncio.to_thread``
    переносит ``contextvars`` в рабочий поток, поэтому вложенные ``timed`` в
    HTTP-клиенте, обходе страниц и хранилище попадают в неё сами. Сводка
    пишется в лог всегда — в том числе когда тулза упала по таймауту, где она
    и нужнее всего.
    """
    timings = Timings()
    started = time.perf_counter()
    try:
        with track(timings), _progress_bridge(ctx):
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
    finally:
        log.info(
            "%s total=%.3fs %s",
            operation or failure,
            time.perf_counter() - started,
            timings.summary(),
        )
