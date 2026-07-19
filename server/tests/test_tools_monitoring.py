"""Тесты тулз мониторинга (in-memory Client, мок storage + сети)."""

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

import avito_mcp_server.tools.monitoring as mon_mod
from fakes import FakeStorage

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
        {
            "id": 3,
            "title": "price same",
            "priceDetailed": {"value": 1000},
            "location": {"name": "NN"},
            "urlPath": "/x_3",
        },
    ]
}


def _mcp() -> FastMCP:
    m = FastMCP("test")
    mon_mod.register(m)
    return m


class _FakeClient:
    pass


class TestScanNewListings:
    async def test_returns_new_and_dropped_only(self, monkeypatch) -> None:
        db = FakeStorage()
        db.upsert_seen(2, "/x_2", "price dropped", 1000)
        db.upsert_seen(3, "/x_3", "price same", 1000)

        monkeypatch.setattr(mon_mod, "page_pause", lambda: 0.0)
        monkeypatch.setattr(mon_mod, "build_http_client", _FakeClient)
        monkeypatch.setattr(mon_mod, "build_storage", lambda: db)
        monkeypatch.setattr(mon_mod, "fetch_catalog", lambda c, u: ("ok", CATALOG))

        async with Client(_mcp()) as client:
            res = await client.call_tool(
                "scan_new_listings", {"url": "https://www.avito.ru/x"}
            )

        assert res.data.count == 2
        assert res.data.new_count == 1
        assert res.data.dropped_count == 1
        new_item = next(i for i in res.data.items if i.is_new)
        assert new_item.listing.id == 1
        dropped = next(i for i in res.data.items if not i.is_new)
        assert dropped.listing.id == 2
        assert dropped.price_delta == pytest.approx(100.0)

    async def test_walks_pages(self, monkeypatch) -> None:
        # Мониторинг должен видеть новинки глубже первой страницы каталога.
        db = FakeStorage()
        page1 = {
            "items": [dict(CATALOG["items"][0])],
            "pager": {"next": "/x?p=2", "current": 1},
        }
        page2 = {"items": [dict(CATALOG["items"][1])], "pager": {"current": 2}}
        seen: list[str] = []

        def _fetch(client, url):
            seen.append(url)
            return ("ok", page1 if len(seen) == 1 else page2)

        monkeypatch.setattr(mon_mod, "page_pause", lambda: 0.0)
        monkeypatch.setattr(mon_mod, "build_http_client", _FakeClient)
        monkeypatch.setattr(mon_mod, "build_storage", lambda: db)
        monkeypatch.setattr(mon_mod, "fetch_catalog", _fetch)

        async with Client(_mcp()) as client:
            res = await client.call_tool(
                "scan_new_listings", {"url": "https://www.avito.ru/x", "pages": 2}
            )

        assert seen == ["https://www.avito.ru/x", "https://www.avito.ru/x?p=2"]
        assert res.data.new_count == 2

    async def test_priceless_listing_is_new_only_once(self, monkeypatch) -> None:
        # Объявление без цены: get_previous_price всегда None, поэтому проверка
        # "prev_price is None" считала его новым при КАЖДОМ скане — вечные дубли
        # в уведомлениях. Признак новизны должен брать upsert_seen.
        db = FakeStorage()
        catalog = {
            "items": [
                {
                    "id": 42,
                    "title": "квартира без цены",
                    "location": {"name": "NN"},
                    "urlPath": "/x_42",
                }
            ]
        }
        monkeypatch.setattr(mon_mod, "page_pause", lambda: 0.0)
        monkeypatch.setattr(mon_mod, "build_http_client", _FakeClient)
        monkeypatch.setattr(mon_mod, "build_storage", lambda: db)
        monkeypatch.setattr(mon_mod, "fetch_catalog", lambda c, u: ("ok", catalog))

        async with Client(_mcp()) as client:
            first = await client.call_tool(
                "scan_new_listings", {"url": "https://www.avito.ru/x"}
            )
            second = await client.call_tool(
                "scan_new_listings", {"url": "https://www.avito.ru/x"}
            )

        assert first.data.new_count == 1
        assert second.data.new_count == 0, "второй скан не должен считать его новым"

    async def test_non_ok_page_errors(self, monkeypatch) -> None:
        db = FakeStorage()
        monkeypatch.setattr(mon_mod, "page_pause", lambda: 0.0)
        monkeypatch.setattr(mon_mod, "build_http_client", _FakeClient)
        monkeypatch.setattr(mon_mod, "build_storage", lambda: db)
        monkeypatch.setattr(mon_mod, "fetch_catalog", lambda c, u: ("softblock", None))

        async with Client(_mcp()) as client:
            with pytest.raises(ToolError):
                await client.call_tool(
                    "scan_new_listings", {"url": "https://www.avito.ru/x"}
                )


class TestGetPriceHistory:
    async def test_returns_history(self, monkeypatch) -> None:
        db = FakeStorage()
        db.upsert_seen(42, "/x_42", "item", 1000)
        db.upsert_seen(42, "/x_42", "item", 900)

        monkeypatch.setattr(mon_mod, "build_storage", lambda: db)

        async with Client(_mcp()) as client:
            res = await client.call_tool("get_price_history", {"listing_id": "42"})

        assert res.data.listing_id == 42
        assert res.data.count == 2
        assert res.data.latest_price == 900
        assert res.data.history[0].price == 900
        assert res.data.history[1].price == 1000

    async def test_empty_for_unknown(self, monkeypatch) -> None:
        db = FakeStorage()
        monkeypatch.setattr(mon_mod, "build_storage", lambda: db)

        async with Client(_mcp()) as client:
            res = await client.call_tool("get_price_history", {"listing_id": "999"})

        assert res.data.count == 0
        assert res.data.latest_price is None

    async def test_url_input_extracts_id(self, monkeypatch) -> None:
        db = FakeStorage()
        db.upsert_seen(7890298070, "/x", "item", 100)
        monkeypatch.setattr(mon_mod, "build_storage", lambda: db)

        async with Client(_mcp()) as client:
            res = await client.call_tool(
                "get_price_history",
                {"listing_id": "https://www.avito.ru/x/slug_7890298070"},
            )

        assert res.data.listing_id == 7890298070
        assert res.data.count == 1
