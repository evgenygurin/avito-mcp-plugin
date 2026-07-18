"""Тесты доменных Pydantic-моделей."""

from avito_mcp_server.models import Listing, SearchResult


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
