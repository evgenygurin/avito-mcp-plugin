"""Тесты gateway-тулзы scan_new_listings (in-memory Client).

Gateway собирает каталог через scraper-движок и делегирует персистент в db
(``persist_scan``). Здесь проверяется оркестрация: обход страниц + передача
собранных объявлений в db. Сама логика dedup/истории — в db/tests.
"""

from fastmcp import Client, FastMCP

import avito_mcp_scraper.tools.catalog as catalog_mod
import avito_mcp_server.tools.monitoring as mon_mod
from avito_mcp_scraper.models import ScanItem, ScanResult
from fakes import FakeHttpClient

CATALOG = {
    "items": [
        {
            "id": 1,
            "title": "new listing",
            "priceDetailed": {"value": 5000},
            "location": {"name": "NN"},
            "urlPath": "/x_1",
        },
        {
            "id": 2,
            "title": "price dropped",
            "priceDetailed": {"value": 900},
            "location": {"name": "NN"},
            "urlPath": "/x_2",
        },
    ]
}


class _FakeClient(FakeHttpClient):
    pass


def _mcp() -> FastMCP:
    m = FastMCP("test")
    mon_mod.register(m)
    return m


async def test_crawls_pages_and_delegates_to_db(monkeypatch) -> None:
    """Gateway не пишет в БД сам: собранные объявления уходят в persist_scan."""
    page1 = {
        "items": [dict(CATALOG["items"][0])],
        "pager": {"next": "/x?p=2", "current": 1},
    }
    page2 = {"items": [dict(CATALOG["items"][1])], "pager": {"current": 2}}
    seen: list[str] = []
    persisted: list[list] = []

    def _fetch(client, url):
        seen.append(url)
        return ("ok", page1 if len(seen) == 1 else page2)

    def _persist(listings):
        persisted.append(listings)
        return ScanResult(items=[ScanItem(listing=x, is_new=True) for x in listings])

    monkeypatch.setattr(catalog_mod, "page_pause", lambda: 0.0)
    monkeypatch.setattr(catalog_mod, "build_http_client", _FakeClient)
    monkeypatch.setattr(catalog_mod, "fetch_catalog", _fetch)
    monkeypatch.setattr(mon_mod, "persist_scan", _persist)

    async with Client(_mcp()) as client:
        res = await client.call_tool(
            "scan_new_listings", {"url": "https://www.avito.ru/x", "pages": 2}
        )

    assert seen == ["https://www.avito.ru/x", "https://www.avito.ru/x?p=2"]
    assert len(persisted) == 1, "persist зовётся один раз на весь обход"
    assert {x.id for x in persisted[0]} == {1, 2}
    assert res.data.new_count == 2


async def test_schema_pages_bounds_and_max_age_description() -> None:
    async with Client(_mcp()) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "scan_new_listings")
    pages_schema = tool.inputSchema["properties"]["pages"]
    assert pages_schema.get("minimum") == 1
    assert pages_schema.get("maximum") is not None
    max_age_schema = tool.inputSchema["properties"]["max_age"]
    assert "секунд" in max_age_schema.get("description", "").lower()
