"""Тесты замера фаз (timing.py).

Без разбивки по фазам «тулза шла 4 минуты» не отвечает на вопрос, что именно
столько шло: покупка кук, ротации IP, сеть Avito, разбор JSON или облачная база.
"""

from __future__ import annotations

import logging

import pytest

from avito_mcp_server.timing import Timings, current_timings, timed, track


@pytest.fixture
def log(caplog, monkeypatch):
    # setup_logging() снимает propagate у логгера пакета (чтобы чужая
    # конфигурация root не дублировала строки) — caplog ловит записи именно
    # через root, поэтому на время теста распространение возвращаем.
    monkeypatch.setattr(logging.getLogger("avito_mcp_server"), "propagate", True)
    caplog.set_level(logging.DEBUG, logger="avito_mcp_server")
    return caplog


def test_timed_logs_stage_and_elapsed(log) -> None:
    with timed("http.get", url="https://www.avito.ru/x"):
        pass

    record = log.records[-1]
    assert "http.get" in record.message
    assert "elapsed=" in record.message
    assert "https://www.avito.ru/x" in record.message


def test_timed_logs_even_on_error(log) -> None:
    # Медленная фаза чаще всего именно та, что упала по таймауту.
    with pytest.raises(RuntimeError), timed("http.get"):
        raise RuntimeError("блокировка")

    assert "http.get" in log.records[-1].message
    assert "failed" in log.records[-1].message


def test_timings_accumulate_by_phase() -> None:
    timings = Timings()
    timings.add("http", 1.5)
    timings.add("http", 0.5)
    timings.add("db", 0.25)

    assert timings.totals() == {"http": 2.0, "db": 0.25}
    assert timings.counts() == {"http": 2, "db": 1}


def test_summary_is_ordered_by_cost() -> None:
    # Самая дорогая фаза — первой: строка читается на бегу в чужом логе.
    timings = Timings()
    timings.add("db", 0.25)
    timings.add("http", 2.0)

    assert timings.summary().startswith("http=2.000s×1")
    assert "db=0.250s×1" in timings.summary()


def test_summary_of_empty_timings_is_readable() -> None:
    assert Timings().summary() == "фаз не было"


def test_timed_feeds_the_active_timings() -> None:
    timings = Timings()
    with track(timings):
        with timed("http"):
            pass
        with timed("http"):
            pass

    assert timings.counts() == {"http": 2}


def test_timed_works_without_active_timings(log) -> None:
    # Замер — не обязанность вызывающего: вне track() фаза просто логируется.
    assert current_timings() is None
    with timed("http"):
        pass
    assert "http" in log.records[-1].message


def test_track_restores_previous_timings() -> None:
    outer = Timings()
    with track(outer):
        with track(Timings()):
            pass
        assert current_timings() is outer
    assert current_timings() is None


def test_timings_are_thread_safe() -> None:
    # check_proxy_health проверяет адреса пула параллельно — счётчики фаз
    # обязаны выдерживать одновременную запись из нескольких потоков.
    import threading

    timings = Timings()

    def _work() -> None:
        for _ in range(200):
            timings.add("http", 0.001)

    threads = [threading.Thread(target=_work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert timings.counts() == {"http": 1600}
