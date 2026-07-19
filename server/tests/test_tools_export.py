"""Тесты тулзы export_listings (in-memory Client)."""

from fastmcp import Client, FastMCP

import avito_mcp_server.tools.exporting as exp_mod


def _mcp() -> FastMCP:
    m = FastMCP("test")
    exp_mod.register(m)
    return m


async def test_export_listings_json_in_memory() -> None:
    items = [
        {"id": 1, "title": "квартира", "price": 5000000, "address": "NN"},
        {"id": 2, "title": "гараж", "price": 900000, "address": "NN"},
    ]
    async with Client(_mcp()) as client:
        res = await client.call_tool("export_listings", {"items": items, "fmt": "json"})

    assert res.data.count == 2
    assert res.data.format == "json"
    assert res.data.path is None
    assert "квартира" in res.data.content
    assert "5000000" in res.data.content


async def test_export_listings_xlsx_to_base64() -> None:
    items = [{"id": 1, "title": "x", "price": 100}]
    async with Client(_mcp()) as client:
        res = await client.call_tool("export_listings", {"items": items, "fmt": "xlsx"})

    assert res.data.count == 1
    assert res.data.format == "xlsx"
    assert len(res.data.content) > 0
    import base64

    decoded = base64.b64decode(res.data.content)
    assert len(decoded) > 0
