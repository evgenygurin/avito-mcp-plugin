"""Провайдер кук: троттлинг покупок и устойчивость к отказу сервиса.

Живой прогон 2026-07-20: агрессивное обновление кук (девять раз за 47 с)
привело к ``429 Too Many Requests`` от самого spfa, и это роняло тулзу целиком
— ``pages=2`` падал за 0.3 с, не сделав ни одного запроса к Avito.

Отсюда два требования. Во-первых, покупки нужно троттлить: каждая стоит денег
(~12 ₽) и лимит сервиса конечен. Во-вторых, отказ провайдера кук — не повод
терять весь вызов: если на руках есть хоть какие-то куки, пробовать надо с
ними, а не падать.
"""

from __future__ import annotations

import httpx
import pytest

from avito_mcp_server.cookies.spfa import SpfaCookiesProvider

_REQ = httpx.Request("POST", "https://spfa.ru/api/cookies/")


def _provider(monkeypatch, responses: list, tmp_path) -> SpfaCookiesProvider:
    calls: list[str] = []

    def _post(url, **kwargs):  # noqa: ANN001, ANN202
        calls.append(url)
        item = (
            responses.pop(0)
            if responses
            else httpx.Response(200, json={}, request=_REQ)
        )
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(httpx, "post", _post)
    prov = SpfaCookiesProvider("key", cache_path=tmp_path / "cookies.json")
    prov.calls = calls  # type: ignore[attr-defined]
    return prov


def test_service_rate_limit_does_not_kill_the_call(monkeypatch, tmp_path) -> None:
    prov = _provider(
        monkeypatch, [httpx.Response(429, text="slow down", request=_REQ)], tmp_path
    )
    prov.last_cookies = {"ft": "старые, но какие-то"}

    # Провайдер отказал — работаем на том, что есть, а не роняем весь парсинг.
    prov.handle_block()

    assert prov.get() == {"ft": "старые, но какие-то"}


def test_rate_limit_without_any_cookies_is_reported(monkeypatch, tmp_path) -> None:
    # Совсем без кук продолжать нечем — тогда ошибка законна.
    prov = _provider(
        monkeypatch, [httpx.Response(429, text="slow down", request=_REQ)], tmp_path
    )
    prov.last_cookies = None

    with pytest.raises(Exception):
        prov.get()


def test_purchases_are_throttled(monkeypatch, tmp_path) -> None:
    ok = httpx.Response(
        200, json={"results": {"id": "1", "cookies": {"ft": "x"}}}, request=_REQ
    )
    prov = _provider(monkeypatch, [ok, ok, ok], tmp_path)

    prov.last_cookies = None
    prov.get()  # первая покупка — законна
    before = len(prov.calls)  # type: ignore[attr-defined]

    # Немедленное повторное обновление не должно превращаться в новую покупку:
    # именно частота привела к 429 от сервиса.
    prov.last_id = None
    prov.handle_block()

    assert len(prov.calls) == before  # type: ignore[attr-defined]


def test_throttle_lets_a_purchase_through_after_the_interval(
    monkeypatch, tmp_path
) -> None:
    ok = httpx.Response(
        200, json={"results": {"id": "1", "cookies": {"ft": "x"}}}, request=_REQ
    )
    prov = _provider(monkeypatch, [ok, ok], tmp_path)
    prov.last_cookies = None
    prov.get()
    before = len(prov.calls)  # type: ignore[attr-defined]

    # Прошло достаточно времени — покупка снова разрешена.
    prov._last_buy = 0.0
    prov.last_id = None
    prov.last_cookies = None
    prov.get()

    assert len(prov.calls) > before  # type: ignore[attr-defined]
