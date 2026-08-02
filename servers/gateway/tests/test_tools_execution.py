"""Тесты общей границы выполнения тулз (tools/execution.py)."""

import threading

import pytest
from fastmcp.exceptions import ToolError

from avito_mcp_server.tools.execution import run_blocking


async def test_returns_action_result() -> None:
    assert await run_blocking(lambda: 42, failure="не вышло") == 42


async def test_runs_action_off_the_event_loop() -> None:
    # Движок парсинга блокирующий: если бы действие исполнялось на петле,
    # один долгий скрап замораживал бы весь сервер.
    loop_thread = threading.current_thread().name
    worker = await run_blocking(
        lambda: threading.current_thread().name, failure="не вышло"
    )
    assert worker != loop_thread


async def test_wraps_arbitrary_error_into_tool_error() -> None:
    def _boom() -> None:
        raise RuntimeError("прокси сдох")

    with pytest.raises(ToolError, match="не вышло: прокси сдох"):
        await run_blocking(_boom, failure="не вышло")


async def test_passes_tool_error_through_without_double_wrapping() -> None:
    def _boom() -> None:
        raise ToolError("уже сформулировано")

    with pytest.raises(ToolError, match="^уже сформулировано$"):
        await run_blocking(_boom, failure="не вышло")
