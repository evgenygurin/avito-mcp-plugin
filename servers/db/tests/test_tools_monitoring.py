"""Тесты db мониторинг-тулз (в-memory Client, мок хранилища).

Проверяем контракт ``record_scan_result`` (перезапись dedup/seen/истории) и
``get_price_history`` через FakeStorage; чистую логику ``_changes`` — в
изоляции (см. ``test_changes_reports_only_price_drops``).
"""

import pytest
from fastmcp import Client, FastMCP

import avito_mcp_db.tools.monitoring as mon_mod
from fakes import FakeStorage


def _row(id: int, price: float | None = None, title: str = "x") -> dict:
    row: dict = {"id": id, "title": title}
    if price is not None:
        row["price"] = price
    return row


def _mcp() -> FastMCP:
    m = FastMCP("test-db")
    mon_mod.register_record(m)
    mon_mod.register_history(m)
    return m


class TestRecordScanResult:
    async def test_returns_new_and_dropped_only(self, monkeypatch) -> None:
        db = FakeStorage()
        db.upsert_seen(2, "/x_2", "price dropped", 1000)
        db.upsert_seen(3, "/x_3", "price same", 1000)
        monkeypatch.setattr(mon_mod, "build_storage", lambda: db)

        listings = [_row(1, 5000), _row(2, 900), _row(3, 1000)]
        async with Client(_mcp()) as client:
            res = await client.call_tool("record_scan_result", {"listings": listings})

        assert res.data.count == 2
        assert res.data.new_count == 1
        assert res.data.dropped_count == 1
        new_item = next(i for i in res.data.items if i.is_new)
        assert new_item.listing.id == 1
        dropped = next(i for i in res.data.items if not i.is_new)
        assert dropped.listing.id == 2
        assert dropped.price_delta == pytest.approx(100.0)

    async def test_storage_roundtrips_do_not_grow_with_catalog_size(
        self, monkeypatch
    ) -> None:
        # НN+1 к Postgres: обращений должно быть O(1), а не O(числа объявлений).
        db = FakeStorage()
        monkeypatch.setattr(mon_mod, "build_storage", lambda: db)

        listings = [_row(i, 1000 + i) for i in range(1, 51)]
        async with Client(_mcp()) as client:
            res = await client.call_tool("record_scan_result", {"listings": listings})

        assert res.data.new_count == 50
        assert db.calls <= 2, f"хранилище звано {db.calls} раз — должно быть O(1)"

    async def test_priceless_listing_is_new_only_once(self, monkeypatch) -> None:
        db = FakeStorage()
        monkeypatch.setattr(mon_mod, "build_storage", lambda: db)
        listing = [_row(42, title="квартира без цены")]

        async with Client(_mcp()) as client:
            first = await client.call_tool("record_scan_result", {"listings": listing})
            second = await client.call_tool("record_scan_result", {"listings": listing})

        assert first.data.new_count == 1
        assert second.data.new_count == 0, (
            "второй вызов не должен считать объявление новым"
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


@pytest.mark.parametrize(
    ("prev_price", "price", "expect_reported"),
    [
        (1000.0, 900.0, True),  # подешевело — единственный повод для отчёта
        (1000.0, 1000.0, False),  # цена та же
        (1000.0, 1100.0, False),  # подорожало
        (None, 900.0, False),  # ранее видели без цены — сравнивать не с чем
        (1000.0, None, False),  # цена пропала — не считаем это скидкой
    ],
)
def test_changes_reports_only_real_price_drops(
    prev_price: float | None, price: float | None, expect_reported: bool
) -> None:
    from avito_mcp_scraper.models import Listing
    from avito_mcp_db.tools.monitoring import _changes

    items = _changes([Listing(id=1, title="x", price=price)], {1: prev_price})
    assert bool(items) is expect_reported
