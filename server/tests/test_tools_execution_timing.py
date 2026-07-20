"""Замер фаз на общей границе выполнения тулз (tools/execution.py).

Копилка фаз заводится один раз здесь, а не в каждой тулзе: тогда любой
вложенный ``timed`` — в HTTP-клиенте, обходе страниц, хранилище — попадает в
сводку без того, чтобы протаскивать её аргументом через пять слоёв.
"""

from __future__ import annotations

import logging

import pytest
from fastmcp.exceptions import ToolError

from avito_mcp_server.timing import current_timings, timed
from avito_mcp_server.tools.execution import run_blocking


@pytest.fixture
def log(caplog, monkeypatch):
    monkeypatch.setattr(logging.getLogger("avito_mcp_server"), "propagate", True)
    caplog.set_level(logging.INFO, logger="avito_mcp_server")
    return caplog


async def test_phase_measured_in_worker_thread_reaches_the_summary(log) -> None:
    # asyncio.to_thread переносит contextvars в рабочий поток — на этом и
    # держится вся схема замеров: движок парсинга ничего не знает о копилке.
    def _work() -> None:
        with timed("http.request"):
            pass

    await run_blocking(_work, failure="не вышло", operation="search_listings")

    summary = [r.message for r in log.records if "search_listings" in r.message]
    assert summary, "сводная строка тулзы не залогирована"
    assert "http.request=" in summary[-1]
    assert "total=" in summary[-1]


async def test_summary_is_logged_even_when_action_fails(log) -> None:
    def _boom() -> None:
        with timed("http.request"):
            raise RuntimeError("блокировка")

    with pytest.raises(ToolError):
        await run_blocking(_boom, failure="не вышло", operation="search_listings")

    summary = [r.message for r in log.records if "search_listings" in r.message]
    assert summary and "http.request=" in summary[-1]


async def test_each_call_gets_a_fresh_timings() -> None:
    # Иначе сводка второй тулзы включала бы фазы первой, и «медленно» нельзя
    # было бы отнести к конкретному вызову.
    counts: list[dict[str, int]] = []

    def _work() -> None:
        with timed("http.request"):
            pass
        timings = current_timings()
        assert timings is not None
        counts.append(timings.counts())

    await run_blocking(_work, failure="не вышло", operation="one")
    await run_blocking(_work, failure="не вышло", operation="two")

    assert counts == [{"http.request": 1}, {"http.request": 1}]


async def test_operation_defaults_to_failure_text(log) -> None:
    # Метка необязательна: тулза, не передавшая её, всё равно попадает в лог.
    await run_blocking(lambda: None, failure="не удалось получить объявления")

    assert any("не удалось получить объявления" in r.message for r in log.records)
