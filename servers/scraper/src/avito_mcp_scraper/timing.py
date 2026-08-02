"""Замер фаз: сколько времени тулза провела в сети, в разборе и в базе.

Общая длительность вызова ничего не объясняет — «четыре минуты» одинаково
выглядят при покупке кук, десяти ротациях IP, медленном облачном Postgres и
многостраничном обходе каталога. Поэтому каждая дорогая операция оборачивается
в :func:`timed`, а вызывающая тулза оборачивает всю работу в :func:`track` и
пишет в лог одну сводную строку.

Копилка передаётся через ``contextvars``, а не аргументом через пять слоёв:
``asyncio.to_thread`` переносит контекст в рабочий поток, поэтому ``HttpClient``
и хранилище видят копилку, заведённую тулзой, ничего о ней не зная. Там, где
работа уходит в свой пул потоков (параллельная проверка прокси), копилка
передаётся в :func:`track` явно.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

log = logging.getLogger(__name__)

__all__ = ["Timings", "current_timings", "timed", "track"]


class Timings:
    """Сумма и число заходов по каждой фазе одного вызова тулзы.

    Потокобезопасна: параллельная проверка адресов прокси пишет сюда из
    нескольких потоков сразу.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._totals: dict[str, float] = {}
        self._counts: dict[str, int] = {}

    def add(self, phase: str, seconds: float) -> None:
        with self._lock:
            self._totals[phase] = self._totals.get(phase, 0.0) + seconds
            self._counts[phase] = self._counts.get(phase, 0) + 1

    def totals(self) -> dict[str, float]:
        with self._lock:
            return dict(self._totals)

    def counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def total(self) -> float:
        """Сумма по всем фазам (фазы могут вкладываться — не равно wall-clock)."""
        with self._lock:
            return sum(self._totals.values())

    def summary(self) -> str:
        """Строка для лога: самая дорогая фаза первой."""
        totals = self.totals()
        if not totals:
            return "фаз не было"
        counts = self.counts()
        ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)
        return " ".join(
            f"{phase}={seconds:.3f}s×{counts[phase]}" for phase, seconds in ordered
        )


_CURRENT: ContextVar[Timings | None] = ContextVar("avito_timings", default=None)


def current_timings() -> Timings | None:
    """Копилка текущего вызова тулзы или ``None`` вне :func:`track`."""
    return _CURRENT.get()


@contextmanager
def track(timings: Timings) -> Iterator[Timings]:
    """Сделать ``timings`` копилкой для всех вложенных :func:`timed`."""
    token = _CURRENT.set(timings)
    try:
        yield timings
    finally:
        _CURRENT.reset(token)


def _fields(fields: dict[str, object]) -> str:
    return "".join(f" {key}={value}" for key, value in fields.items())


@contextmanager
def timed(
    phase: str, logger: logging.Logger | None = None, **fields: object
) -> Iterator[None]:
    """Замерить блок: записать в активную копилку и залогировать длительность.

    Логирует и при исключении (пометкой ``failed``): самая медленная фаза чаще
    всего именно та, что упёрлась в таймаут и упала.

    Args:
        phase: имя фазы (``http.get``, ``cookies.buy``, ``db.upsert``).
        logger: логгер вызывающего модуля; по умолчанию — логгер этого модуля.
        fields: контекст в строку лога (url, proxy, статус) — уже
            замаскированный, секретам в логе не место.
    """
    started = time.perf_counter()
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        elapsed = time.perf_counter() - started
        timings = _CURRENT.get()
        if timings is not None:
            timings.add(phase, elapsed)
        mark = " failed" if failed else ""
        (logger or log).info(
            "%s elapsed=%.3fs%s%s", phase, elapsed, mark, _fields(fields)
        )
