"""Backoff после ротации IP: цена паузы по данным живого прогона.

Замеры 2026-07-20 (мобильный прокси, RU): сам запрос к Avito — 0.6–0.8 с,
смена IP через кабинет — 3.6–4.3 с, а пауза после неё — 9 с и дальше по
удвоению. То есть в ожидании уходило на порядок больше времени, чем в полезной
работе, причём ждали мы уже ПОСЛЕ смены выходного адреса.

Отсюда два изменения: пауза настраивается из окружения, а время, потраченное
на саму ротацию, засчитывается в неё — ждать 9 с после того, как четыре
секунды уже прошли и IP сменился, смысла нет.
"""

from __future__ import annotations

import avito_mcp_server.config as config_mod
import avito_mcp_server.http.client as hc
from avito_mcp_server.http.client import HttpClient


class _Resp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeSession:
    seq: list = []

    def get(self, url, cookies=None, timeout=None, allow_redirects=True):  # noqa: ANN001, ANN201
        return _FakeSession.seq.pop(0)

    def close(self) -> None:
        pass


class _SlowRotatingProxy:
    """Прокси, у которого смена IP занимает время — как настоящий мобильный."""

    def __init__(self, rotate_cost: float) -> None:
        self.rotate_cost = rotate_cost
        self.clock = 0.0

    def httpx_proxy(self) -> str:
        return "http://x"

    def rotate(self) -> bool:
        self.clock += self.rotate_cost
        return True


def _run(monkeypatch, proxy, **kwargs) -> list[float]:
    """Прогнать клиент до отказа и вернуть список фактических пауз."""
    waited: list[float] = []
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    monkeypatch.setattr(hc, "_sleep", waited.append)
    # Часы, которые двигает только ротация: замер паузы должен опираться на
    # время, а не на то, что вернул proxy.rotate().
    monkeypatch.setattr(hc.time, "monotonic", lambda: proxy.clock)

    client = HttpClient(proxy=proxy, cookies=None, **kwargs)
    try:
        client.get("https://www.avito.ru/x")
    except RuntimeError:
        pass
    return waited


def test_rotation_time_counts_towards_the_pause(monkeypatch) -> None:
    _FakeSession.seq = [_Resp(403) for _ in range(10)]
    proxy = _SlowRotatingProxy(rotate_cost=4.0)

    waited = _run(
        monkeypatch, proxy, max_attempts=4, wait_after_rotate=3.0, backoff_cap=60.0
    )

    # Первая пауза 3 с уже «отработана» четырьмя секундами ротации → не спим.
    # Вторая (6 с) и третья (12 с) — минус те же 4 с.
    assert waited == [0.0, 2.0, 8.0]


def test_pause_never_goes_negative(monkeypatch) -> None:
    _FakeSession.seq = [_Resp(403) for _ in range(10)]
    proxy = _SlowRotatingProxy(rotate_cost=30.0)

    waited = _run(
        monkeypatch, proxy, max_attempts=3, wait_after_rotate=3.0, backoff_cap=60.0
    )

    assert waited == [0.0, 0.0]


def test_wait_after_rotate_comes_from_env(monkeypatch) -> None:
    monkeypatch.setenv("AVITO_ROTATE_WAIT", "1.5")
    monkeypatch.setenv("AVITO_PROXY", "user:pass@10.0.0.1:8000")
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "none")
    monkeypatch.delenv("AVITO_PROXY_LIST_URL", raising=False)
    monkeypatch.delenv("AVITO_SUPABASE_DSN", raising=False)

    client = config_mod.build_http_client()

    assert client.wait_after_rotate == 1.5


def test_default_wait_is_shorter_than_the_old_nine_seconds(monkeypatch) -> None:
    # 9 с на первой блокировке — это половина минуты на три попытки при
    # запросе в 0.7 с. Дефолт должен быть заметно скромнее.
    monkeypatch.delenv("AVITO_ROTATE_WAIT", raising=False)
    monkeypatch.setenv("AVITO_PROXY", "user:pass@10.0.0.1:8000")
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "none")
    monkeypatch.delenv("AVITO_PROXY_LIST_URL", raising=False)
    monkeypatch.delenv("AVITO_SUPABASE_DSN", raising=False)

    client = config_mod.build_http_client()

    assert 0 < client.wait_after_rotate <= 3.0


def test_broken_env_value_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setenv("AVITO_ROTATE_WAIT", "почти сразу")
    monkeypatch.setenv("AVITO_PROXY", "user:pass@10.0.0.1:8000")
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "none")
    monkeypatch.delenv("AVITO_PROXY_LIST_URL", raising=False)
    monkeypatch.delenv("AVITO_SUPABASE_DSN", raising=False)

    client = config_mod.build_http_client()

    assert client.wait_after_rotate > 0
