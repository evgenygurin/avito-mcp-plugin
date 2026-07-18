"""Тесты тулзы search_listings (in-memory Client, мок сетевой границы)."""

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

import avito_mcp_server.tools.search as search_mod

CATALOG = {
    "items": [
        {
            "id": 1,
            "title": "1-к квартира",
            "priceDetailed": {"value": 5000000},
            "location": {"name": "Нижний Новгород"},
            "urlPath": "/x_1",
        },
        {
            "id": 2,
            "title": "гараж",
            "priceDetailed": {"value": 900000},
            "location": {"name": "Нижний Новгород"},
            "urlPath": "/x_2",
        },
    ]
}


def _mcp() -> FastMCP:
    m = FastMCP("test")
    search_mod.register(m)
    return m


async def test_search_listings_returns_filtered(monkeypatch) -> None:
    monkeypatch.setattr(search_mod, "build_http_client", lambda: object())
    monkeypatch.setattr(
        search_mod, "fetch_catalog", lambda client, url: ("ok", CATALOG)
    )

    async with Client(_mcp()) as client:
        res = await client.call_tool(
            "search_listings",
            {
                "url": "https://www.avito.ru/nn/kvartiry",
                "include_keywords": ["квартира"],
            },
        )

    assert res.data.count == 1
    assert res.data.items[0].id == 1
    assert res.data.items[0].url == "https://www.avito.ru/x_1"


async def test_search_listings_errors_on_non_ok(monkeypatch) -> None:
    monkeypatch.setattr(search_mod, "build_http_client", lambda: object())
    monkeypatch.setattr(
        search_mod, "fetch_catalog", lambda client, url: ("softblock", None)
    )

    async with Client(_mcp()) as client:
        with pytest.raises(ToolError):
            await client.call_tool(
                "search_listings", {"url": "https://www.avito.ru/nn"}
            )
