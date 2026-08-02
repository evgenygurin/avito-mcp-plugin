"""Тесты тулзы get_listing (in-memory Client, мок сетевой границы)."""

from pathlib import Path

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

import avito_mcp_server.tools.listings as listings_mod
from fakes import FakeHttpClient

FIX = Path(__file__).parent / "fixtures"


class _FakeHttpClient(FakeHttpClient):
    def get(self, url: str, max_attempts: int | None = None):
        html = (FIX / "listing_detail.html").read_text(encoding="utf-8")
        from unittest.mock import Mock

        resp = Mock()
        resp.text = html
        return resp


def _mcp() -> FastMCP:
    m = FastMCP("test")
    listings_mod.register(m)
    return m


async def test_get_listing_by_url(monkeypatch) -> None:
    monkeypatch.setattr(listings_mod, "build_http_client", _FakeHttpClient)

    async with Client(_mcp()) as client:
        res = await client.call_tool(
            "get_listing",
            {
                "id_or_url": "https://www.avito.ru/nizhniy_novgorod/kvartiry/x_7890298070",
                "with_views": True,
            },
        )

    assert res.data.id == 7890298070
    assert res.data.title == "1-к. квартира, 45 м², 5/9 эт."
    assert res.data.price == 5500000
    assert (
        res.data.description
        == "Продаётся отличная квартира в центре города. Рядом метро."
    )
    assert res.data.views == 1234
    assert res.data.params == {
        "Площадь": "45 м²",
        "Этаж": "5 из 9",
        "Тип дома": "кирпичный",
    }


async def test_get_listing_by_id(monkeypatch) -> None:
    monkeypatch.setattr(listings_mod, "build_http_client", _FakeHttpClient)

    async with Client(_mcp()) as client:
        res = await client.call_tool(
            "get_listing",
            {"id_or_url": "7890298070"},
        )

    assert res.data.id == 7890298070


async def test_get_listing_errors_on_missing_data(monkeypatch) -> None:
    fake = _FakeHttpClient()

    from unittest.mock import Mock

    def _empty(url: str, max_attempts: int | None = None):
        resp = Mock()
        resp.text = "<html>no data</html>"
        return resp

    fake.get = _empty  # type: ignore[method-assign]
    monkeypatch.setattr(listings_mod, "build_http_client", lambda: fake)

    async with Client(_mcp()) as client:
        with pytest.raises(ToolError):
            await client.call_tool(
                "get_listing", {"id_or_url": "https://www.avito.ru/x"}
            )


async def test_get_listing_follows_ssr_redirect(monkeypatch) -> None:
    # Карточка объявления тоже приходит SSR-редиректом на канонический URL:
    # без хопа парсер видит страницу-редирект и объявление «не находится».
    from unittest.mock import Mock

    redirect = (
        '<script type="mime/invalid" data-mfe-state="true">'
        '{"i18n":{"hasMessages":true},"loaderData":{"data":'
        '{"redirected":true,"url":"/items/7890298070"}}}</script>'
    )
    detail = (FIX / "listing_detail.html").read_text(encoding="utf-8")
    pages = {"https://www.avito.ru/x": redirect}
    seen: list[str] = []

    class _Redirecting(FakeHttpClient):
        def get(self, url: str, max_attempts: int | None = None):
            seen.append(url)
            resp = Mock()
            resp.text = pages.get(url, detail)
            return resp

    monkeypatch.setattr(listings_mod, "build_http_client", _Redirecting)

    async with Client(_mcp()) as client:
        res = await client.call_tool(
            "get_listing", {"id_or_url": "https://www.avito.ru/x"}
        )

    assert seen == ["https://www.avito.ru/x", "https://www.avito.ru/items/7890298070"]
    assert res.data.id == 7890298070
