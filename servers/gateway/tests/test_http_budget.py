"""Жёсткий бюджет времени на вызов: почему без него тулза «висит».

Лимиты попыток перемножаются: ``max_attempts`` (5) × ``max_token_refreshes``
(3) × ``_REDIRECT_HOP_ATTEMPTS`` (5) × два круга эскалации. Верхней границы по
времени у этой конструкции нет — живой прогон 2026-07-20 дал 10 запросов,
9 ротаций и 2 эскалации, когда ``timeout=180`` у тулзы давно истёк.

Важно, что таймаут тулзы тут не спасает: работа идёт в ``asyncio.to_thread``,
который нельзя отменить. Клиент получает отказ, а поток продолжает жечь
платные ротации в фоне — со стороны это и выглядит как зависание. Значит
останавливаться движок обязан сам.
"""

from __future__ import annotations

import pytest

import avito_mcp_server.http.client as hc
from avito_mcp_server.http.client import HttpClient


class _Resp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeSession:
    seq: list = []

    def get(self, url, cookies=None, timeout=None, allow_redirects=True):  # noqa: ANN001, ANN201
        return _FakeSession.seq.pop(0) if _FakeSession.seq else _Resp(403)

    def close(self) -> None:
        pass


class _Clock:
    """Управляемые часы: время двигают ротации и сон, а не реальное ожидание."""

    def __init__(self) -> None:
        self.now = 0.0

    def tick(self, seconds: float) -> None:
        self.now += seconds


class _SlowProxy:
    def __init__(self, clock: _Clock, rotate_cost: float = 4.0) -> None:
        self.clock = clock
        self.rotate_cost = rotate_cost
        self.rotations = 0
        self.escalations = 0

    def httpx_proxy(self) -> str:
        return "http://x"

    def rotate(self) -> bool:
        self.rotations += 1
        self.clock.tick(self.rotate_cost)
        return True

    def escalate(self) -> bool:
        self.escalations += 1
        self.clock.tick(2.0)
        return True


@pytest.fixture
def wired(monkeypatch):
    clock = _Clock()
    _FakeSession.seq = []
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    monkeypatch.setattr(hc.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(hc, "_sleep", clock.tick)
    return clock


def test_budget_stops_the_attempt_loop(wired) -> None:
    proxy = _SlowProxy(wired)
    client = HttpClient(
        proxy=proxy, cookies=None, max_attempts=50, wait_after_rotate=3.0, budget=20.0
    )

    with pytest.raises(RuntimeError, match="бюджет"):
        client.get("https://www.avito.ru/x")

    assert wired.now <= 25.0, f"движок ушёл за бюджет: {wired.now:.1f}s"


def test_budget_blocks_escalation_to_a_second_round(wired) -> None:
    # Эскалация запускает ПОЛНЫЙ круг попыток заново — самый дорогой шаг.
    # Бюджет заведомо кончается на первом круге (три попытки по ~4 с ротации).
    proxy = _SlowProxy(wired)
    client = HttpClient(
        proxy=proxy, cookies=None, max_attempts=3, wait_after_rotate=3.0, budget=8.0
    )

    with pytest.raises(RuntimeError):
        client.get("https://www.avito.ru/x")

    assert proxy.escalations == 0


def test_sleep_is_clipped_to_the_remaining_budget(wired) -> None:
    slept: list[float] = []

    def _record(seconds: float) -> None:
        slept.append(seconds)
        wired.tick(seconds)

    proxy = _SlowProxy(wired, rotate_cost=0.0)
    client = HttpClient(
        proxy=proxy, cookies=None, max_attempts=50, wait_after_rotate=10.0, budget=25.0
    )
    import avito_mcp_server.http.client as module

    module._sleep = _record  # часы уже подменены фикстурой
    try:
        with pytest.raises(RuntimeError):
            client.get("https://www.avito.ru/x")
    finally:
        module._sleep = wired.tick

    assert sum(slept) <= 25.0
    assert all(seconds >= 0 for seconds in slept)


def test_without_budget_behaviour_is_unchanged(wired) -> None:
    # Бюджет — опция: скрипты и тесты, которым он не нужен, работают как раньше.
    proxy = _SlowProxy(wired)
    client = HttpClient(
        proxy=proxy, cookies=None, max_attempts=3, wait_after_rotate=0, budget=None
    )

    with pytest.raises(RuntimeError, match="попыток"):
        client.get("https://www.avito.ru/x")

    assert proxy.escalations == 1


def test_successful_request_within_budget_is_not_affected(wired) -> None:
    _FakeSession.seq = [_Resp(200, "ok")]
    client = HttpClient(
        proxy=_SlowProxy(wired), cookies=None, max_attempts=3, budget=30.0
    )

    assert client.get("https://www.avito.ru/x").status_code == 200


def test_error_message_names_the_budget(wired) -> None:
    client = HttpClient(
        proxy=_SlowProxy(wired), cookies=None, max_attempts=50, budget=10.0
    )

    with pytest.raises(RuntimeError) as excinfo:
        client.get("https://www.avito.ru/x")

    message = str(excinfo.value)
    assert "10" in message and "AVITO_REQUEST_BUDGET" in message
