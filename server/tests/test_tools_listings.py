"""Тесты тулзы get_listing (in-memory Client, мок сетевой границы)."""

from pathlib import Path

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

import avito_mcp_server.tools.listings as listings_mod
from avito_mcp_server.proxies.proxy import NoProxy

FIX = Path(__file__).parent / "fixtures"


class _FakeHttpClient:
    proxy = NoProxy()

    def get(self, url: str):
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

    def _empty(url: str):
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
