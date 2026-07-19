"""Тесты доменных Pydantic-моделей."""

from avito_mcp_server.models import (
    ExportResult,
    Listing,
    NotificationResult,
    PriceHistoryResult,
    PricePoint,
    ScanItem,
    ScanResult,
    SearchResult,
)


class TestListing:
    def test_minimal_has_optional_fields(self) -> None:
        item = Listing(id=1, title="iPhone 15")
        assert item.price is None
        assert item.params == {}
        assert item.is_promotion is False
        assert item.views is None

    def test_full_facts(self) -> None:
        item = Listing(
            id=7890298070,
            title="7-к. квартира, 306,5 м²",
            price=98630444,
            url="https://www.avito.ru/nizhniy_novgorod/kvartiry/x_7890298070",
            address="Нижний Новгород",
            params={"площадь": "306,5 м²"},
            seller_id="brand",
            is_promotion=True,
            published_at=1700000000,
            views=42,
        )
        assert item.price == 98630444
        assert item.address == "Нижний Новгород"
        assert item.seller_id == "brand"
        assert item.views == 42

    def test_no_pii_phone_field(self) -> None:
        # Телефоны продавцов (ПДн) не моделируем.
        assert "phone" not in Listing.model_fields


class TestSearchResult:
    def test_count_is_derived(self) -> None:
        res = SearchResult(items=[Listing(id=1, title="a"), Listing(id=2, title="b")])
        assert res.count == 2

    def test_empty(self) -> None:
        assert SearchResult(items=[]).count == 0


class TestScanResult:
    def test_counts_new_and_dropped(self) -> None:
        items = [
            ScanItem(listing=Listing(id=1, title="new"), is_new=True),
            ScanItem(
                listing=Listing(id=2, title="dropped", price=1000),
                is_new=False,
                price_delta=500,
            ),
        ]
        res = ScanResult(items=items)
        assert res.count == 2
        assert res.new_count == 1
        assert res.dropped_count == 1

    def test_empty(self) -> None:
        res = ScanResult(items=[])
        assert res.count == 0
        assert res.new_count == 0
        assert res.dropped_count == 0


class TestPriceHistoryResult:
    def test_latest_price_and_count(self) -> None:
        history = [
            PricePoint(price=1000, seen_at=1700000000),
            PricePoint(price=1200, seen_at=1699000000),
        ]
        res = PriceHistoryResult(listing_id=42, history=history)
        assert res.count == 2
        assert res.latest_price == 1000

    def test_empty_history(self) -> None:
        res = PriceHistoryResult(listing_id=42, history=[])
        assert res.count == 0
        assert res.latest_price is None


class TestExportResult:
    def test_export_result(self) -> None:
        res = ExportResult(format="json", content='[{"id":1}]', count=1)
        assert res.format == "json"
        assert res.path is None
        assert res.count == 1

    def test_export_with_path(self) -> None:
        res = ExportResult(format="xlsx", path="/tmp/out.xlsx", count=5)
        assert res.content is None
        assert res.path == "/tmp/out.xlsx"


class TestNotificationResult:
    def test_notification_ok(self) -> None:
        res = NotificationResult(
            channel="telegram", sent=True, targets=["123"], detail="ok"
        )
        assert res.sent is True
        assert res.targets == ["123"]


def test_proxy_probe_masks_credentials() -> None:
    # В строке прокси лежат логин и пароль — наружу отдаём только host:port.
    from avito_mcp_server.utils import mask_proxy

    assert mask_proxy("user:secret@1.2.3.4:8000") == "1.2.3.4:8000"
    assert mask_proxy("1.2.3.4:8000") == "1.2.3.4:8000"
    assert mask_proxy("") == ""
