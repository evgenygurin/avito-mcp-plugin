"""Тесты моста прогресса поток → MCP-клиент (progress.py, tools/execution.py).

Обход десяти страниц каталога с ротациями IP идёт минутами. Без прогресса
клиент видит тишину и не отличает работу от зависания — а отменить
``asyncio.to_thread`` нельзя, так что «просто подождать» стоит дорого.
"""

from __future__ import annotations

import threading

import pytest

from avito_mcp_server.progress import report, sink
from avito_mcp_server.tools.execution import run_blocking


class _Ctx:
    """Заглушка ``fastmcp.Context``: пишет всё, что ей отправили."""

    def __init__(self) -> None:
        self.progress: list[tuple[float, float | None, str | None]] = []

    async def report_progress(
        self,
        progress: float,
        total: float | None = None,
        message: str | None = None,
    ) -> None:
        self.progress.append((progress, total, message))


def test_report_without_sink_is_a_noop() -> None:
    # Движок парсинга вызывается и из тестов, и из скриптов — без активного
    # приёмника отчёт о прогрессе не должен ничего требовать.
    report(1, 3, "страница 1/3")


def test_report_reaches_the_sink() -> None:
    seen: list[tuple[float, float | None, str | None]] = []
    with sink(lambda *args: seen.append(args)):
        report(1, 3, "страница 1/3")

    assert seen == [(1, 3, "страница 1/3")]


def test_sink_is_restored_after_exit() -> None:
    with sink(lambda *args: None):
        pass
    report(1, 1, "после выхода")  # не должно падать


async def test_progress_from_worker_thread_reaches_the_context() -> None:
    ctx = _Ctx()

    def _work() -> str:
        assert threading.current_thread() is not threading.main_thread()
        report(1, 2, "страница 1/2")
        report(2, 2, "страница 2/2")
        return "готово"

    assert await run_blocking(_work, failure="не вышло", ctx=ctx) == "готово"
    assert ctx.progress == [(1, 2, "страница 1/2"), (2, 2, "страница 2/2")]


async def test_broken_progress_never_breaks_the_tool() -> None:
    # Отчёт о прогрессе — вспомогательный канал: клиент, который его не
    # поддерживает, не повод терять уже собранные объявления.
    class _Broken(_Ctx):
        async def report_progress(self, *args, **kwargs) -> None:
            raise RuntimeError("клиент не поддерживает прогресс")

    def _work() -> str:
        report(1, 1, "страница 1/1")
        return "готово"

    assert await run_blocking(_work, failure="не вышло", ctx=_Broken()) == "готово"


async def test_no_context_means_no_progress_plumbing() -> None:
    def _work() -> str:
        report(1, 1, "страница 1/1")
        return "готово"

    assert await run_blocking(_work, failure="не вышло") == "готово"


async def test_walk_pages_reports_each_page() -> None:
    from avito_mcp_server.parser import PageKind, walk_pages

    seen: list[tuple[float, float | None, str | None]] = []
    catalog = {"items": [], "pager": {"next": "/nn/kvartiry?p=2"}}

    def _fetch(client: object, url: str):
        return PageKind.OK, catalog

    with sink(lambda *args: seen.append(args)):
        walk_pages(_fetch, object(), "https://www.avito.ru/nn/kvartiry", pages=3)

    assert [item[0] for item in seen] == [1, 2, 3]
    assert all(item[1] == 3 for item in seen)


@pytest.mark.parametrize("pages", [1, 2])
def test_walk_pages_progress_is_optional(pages: int) -> None:
    from avito_mcp_server.parser import PageKind, walk_pages

    def _fetch(client: object, url: str):
        return PageKind.OK, {"items": [], "pager": {"next": "/nn?p=2"}}

    walk_pages(_fetch, object(), "https://www.avito.ru/nn", pages=pages)
