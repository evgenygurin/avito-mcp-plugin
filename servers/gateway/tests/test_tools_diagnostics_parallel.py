"""Параллельная проверка адресов пула в check_proxy_health.

Проба каждого адреса — это сетевой запрос до 20 с таймаута, и адреса
независимы. Последовательный обход пула из двух десятков адресов упирался в
собственный ``timeout=180`` тулзы раньше, чем доходил до конца, — то есть
диагностика не могла отработать именно тогда, когда пул большой и её ответ
нужнее всего.
"""

from __future__ import annotations

import threading
import time

import avito_mcp_server.tools.diagnostics as diag


def test_probes_run_concurrently(monkeypatch) -> None:
    urls = [f"user:pass@10.0.0.{i}:8000" for i in range(1, 9)]
    monkeypatch.setattr(diag, "MAX_PROBE_WORKERS", 8)

    def _slow_probe(client: object, url: str) -> tuple[bool, str]:
        time.sleep(0.2)
        return True, "каталог получен"

    started = time.perf_counter()
    probes = diag.probe_pool(
        urls, cookies=None, probe_url="https://x", probe=_slow_probe
    )
    elapsed = time.perf_counter() - started

    assert len(probes) == 8
    assert elapsed < 0.9, f"пробы шли последовательно: {elapsed:.2f}s"


def test_results_keep_pool_order(monkeypatch) -> None:
    # Порядок в ответе тулзы должен совпадать с порядком адресов в конфиге,
    # иначе «третий адрес мёртв» невозможно сопоставить с настройкой.
    urls = ["user:pass@10.0.0.1:8000", "user:pass@10.0.0.2:8000"]
    delays = {"10.0.0.1:8000": 0.2, "10.0.0.2:8000": 0.0}

    def _probe(client: object, url: str) -> tuple[bool, str]:
        time.sleep(delays[client.proxy.url.rsplit("@", 1)[-1]])  # type: ignore[attr-defined]
        return True, "каталог получен"

    probes = diag.probe_pool(urls, cookies=None, probe_url="https://x", probe=_probe)

    assert [p.proxy for p in probes] == ["10.0.0.1:8000", "10.0.0.2:8000"]


def test_credentials_never_leak_into_the_result() -> None:
    probes = diag.probe_pool(
        ["user:s3cret@10.0.0.1:8000"],
        cookies=None,
        probe_url="https://x",
        probe=lambda client, url: (True, "каталог получен"),
    )

    assert probes[0].proxy == "10.0.0.1:8000"
    assert "s3cret" not in probes[0].proxy


def test_failing_probe_does_not_break_the_rest() -> None:
    urls = ["user:pass@10.0.0.1:8000", "user:pass@10.0.0.2:8000"]

    def _probe(client: object, url: str) -> tuple[bool, str]:
        if "10.0.0.1" in client.proxy.url:  # type: ignore[attr-defined]
            raise RuntimeError("прокси мёртв")
        return True, "каталог получен"

    probes = diag.probe_pool(urls, cookies=None, probe_url="https://x", probe=_probe)

    assert [p.ok for p in probes] == [False, True]
    assert "прокси мёртв" in probes[0].detail


def test_worker_count_is_bounded(monkeypatch) -> None:
    # Пул на сотню адресов не должен поднимать сотню потоков и сотню
    # одновременных соединений через одного провайдера.
    monkeypatch.setattr(diag, "MAX_PROBE_WORKERS", 4)
    peak = 0
    active = 0
    lock = threading.Lock()

    def _probe(client: object, url: str) -> tuple[bool, str]:
        nonlocal peak, active
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return True, "каталог получен"

    diag.probe_pool(
        [f"user:pass@10.0.0.{i}:8000" for i in range(1, 21)],
        cookies=None,
        probe_url="https://x",
        probe=_probe,
    )

    assert peak <= 4


def test_probe_clients_get_a_time_budget(monkeypatch) -> None:
    # Диагностика обязана ответить быстро: без бюджета проба одного адреса
    # уходила в полный rotate-until-clean и переживала timeout самой тулзы
    # (asyncio.to_thread не отменяется — поток жёг ротации уже после отказа).
    budgets: list[float | None] = []

    def _probe(client, url):  # noqa: ANN001, ANN202
        budgets.append(client.budget)
        return True, "каталог получен"

    diag.probe_pool(
        ["user:pass@10.0.0.1:8000"], cookies=None, probe_url="https://x", probe=_probe
    )

    assert budgets and budgets[0] is not None
    assert budgets[0] <= 60.0
