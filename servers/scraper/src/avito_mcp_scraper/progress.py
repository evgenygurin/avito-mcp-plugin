"""Отчёт о прогрессе из блокирующего движка в MCP-клиент.

Обход каталога идёт в рабочем потоке (``asyncio.to_thread``), а
``ctx.report_progress`` — корутина на петле событий. Мост между ними живёт в
``tools/execution.py``; здесь — только точка вызова для движка.

Приёмник передаётся через ``contextvars`` по той же причине, что и копилка
замеров (:mod:`avito_mcp_server.timing`): обход страниц не должен знать ни про
MCP, ни про то, кто его вызвал. Вне тулзы (тесты, скрипты) приёмника нет и
:func:`report` — пустышка.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

#: ``(сделано, всего, сообщение) -> None``. Всего может быть неизвестно.
ProgressSink = Callable[[float, float | None, str | None], None]

_CURRENT: ContextVar[ProgressSink | None] = ContextVar("avito_progress", default=None)

__all__ = ["ProgressSink", "report", "sink"]


def report(
    current: float, total: float | None = None, message: str | None = None
) -> None:
    """Сообщить о прогрессе, если приёмник активен; иначе ничего не делать."""
    active = _CURRENT.get()
    if active is not None:
        active(current, total, message)


@contextmanager
def sink(target: ProgressSink) -> Iterator[None]:
    """Сделать ``target`` приёмником прогресса для вложенного кода."""
    token = _CURRENT.set(target)
    try:
        yield
    finally:
        _CURRENT.reset(token)
