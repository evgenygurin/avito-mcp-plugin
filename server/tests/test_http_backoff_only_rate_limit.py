"""Ждать имеет смысл только при 429, а не при 403.

Это разные отказы. 429 — «слишком часто», лечится паузой. 403 — «этот IP или
эти куки в бане у Qrator», и пауза его не лечит: репутация адреса не
восстанавливается за 48 секунд. Лечится он сменой комбинации (транспорт, куки,
IP), а она мгновенна или стоит секунды.

Живой прогон 2026-07-20 показал цену смешения: из 120 с бюджета
``backoff.sleep=90.6s`` при ``http.request=3.7s`` полезной работы, причём в
логе 11 ответов 403 против 2 ответов 429. То есть 75% времени тулза спала,
дожидаясь, пока «остынет» то, что не остывает.
"""

from __future__ import annotations

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


class _RotatingProxy:
    def httpx_proxy(self) -> str:
        return "http://x"

    def rotate(self) -> bool:
        return True


def _run(monkeypatch, responses, **kwargs) -> list[float]:
    slept: list[float] = []
    _FakeSession.seq = list(responses)
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    monkeypatch.setattr(hc, "_sleep", slept.append)
    client = HttpClient(proxy=_RotatingProxy(), cookies=None, **kwargs)
    try:
        client.get("https://www.avito.ru/x")
    except RuntimeError:
        pass
    return slept


def test_no_sleep_on_403(monkeypatch) -> None:
    slept = _run(
        monkeypatch,
        [_Resp(403) for _ in range(4)],
        max_attempts=4,
        wait_after_rotate=30.0,
    )

    assert slept == [], f"403 лечится сменой IP/кук, а не сном: {slept}"


def test_still_sleeps_on_429(monkeypatch) -> None:
    slept = _run(
        monkeypatch,
        [_Resp(429) for _ in range(3)],
        max_attempts=3,
        wait_after_rotate=5.0,
    )

    assert slept and all(s > 0 for s in slept), "429 — это rate limit, пауза нужна"


def test_mixed_codes_sleep_only_for_the_rate_limited_ones(monkeypatch) -> None:
    slept = _run(
        monkeypatch,
        [_Resp(403), _Resp(429), _Resp(403), _Resp(200, "ok")],
        max_attempts=5,
        wait_after_rotate=4.0,
    )

    assert len(slept) == 1, f"спали не только на 429: {slept}"


def test_success_after_403_costs_no_waiting(monkeypatch) -> None:
    # Тот самый горячий путь: первая комбинация забанена, вторая работает.
    slept = _run(
        monkeypatch,
        [_Resp(403), _Resp(200, "ok")],
        max_attempts=3,
        wait_after_rotate=60.0,
    )

    assert slept == []
