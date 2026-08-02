"""Бюджет времени должен расти вместе с объёмом работы.

Клиент один на весь обход каталога (он же держит TLS-соединение), поэтому
фиксированный бюджет обрезал бы законный многостраничный запрос на середине:
десять страниц — это десять запросов плюс редирект-хопы, и укладывать их в тот
же потолок, что и одну страницу, неправильно.
"""

from __future__ import annotations

import avito_mcp_server.config as config_mod
import avito_mcp_server.tools.catalog as catalog_mod
from avito_mcp_server.filters.filters import FilterSpec


def _env(monkeypatch) -> None:
    monkeypatch.setenv("AVITO_PROXY", "user:pass@10.0.0.1:8000")
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "none")
    monkeypatch.delenv("AVITO_PROXY_LIST_URL", raising=False)
    monkeypatch.delenv("AVITO_SUPABASE_DSN", raising=False)
    monkeypatch.delenv("AVITO_REQUEST_BUDGET", raising=False)


def test_single_page_gets_the_base_budget(monkeypatch) -> None:
    _env(monkeypatch)
    client = config_mod.build_http_client()
    assert client.budget == config_mod.DEFAULT_REQUEST_BUDGET


def test_budget_scales_with_pages(monkeypatch) -> None:
    _env(monkeypatch)
    client = config_mod.build_http_client(budget_scale=5)
    assert client.budget == config_mod.DEFAULT_REQUEST_BUDGET * 5


def test_disabled_budget_stays_disabled(monkeypatch) -> None:
    _env(monkeypatch)
    monkeypatch.setenv("AVITO_REQUEST_BUDGET", "0")
    client = config_mod.build_http_client(budget_scale=5)
    assert client.budget is None


def test_catalog_walk_asks_for_a_budget_per_page(monkeypatch) -> None:
    seen: list[int] = []

    def _build(budget_scale: int = 1):  # noqa: ANN202
        seen.append(budget_scale)
        from fakes import FakeHttpClient

        return FakeHttpClient()

    monkeypatch.setattr(catalog_mod, "build_http_client", _build)
    monkeypatch.setattr(catalog_mod, "page_pause", lambda: 0)
    monkeypatch.setattr(catalog_mod, "walk_pages", lambda *args, **kwargs: [])

    catalog_mod.collect_listings(
        "https://www.avito.ru/x", FilterSpec.from_optional(), 7
    )

    assert seen == [7]
