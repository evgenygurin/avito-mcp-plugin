"""Тесты доменных Pydantic-моделей."""

import pytest
from pydantic import ValidationError

from avito_mcp_server.models import (
    AccountInfo,
    Listing,
    OwnItem,
    OwnItemsResult,
    SearchQuery,
    SearchResult,
)


class TestSearchQuery:
    def test_defaults(self) -> None:
        q = SearchQuery(query="iphone 15")
        assert q.region is None
        assert q.limit == 50

    def test_rejects_empty_query(self) -> None:
        with pytest.raises(ValidationError):
            SearchQuery(query="   ")

    def test_rejects_nonpositive_limit(self) -> None:
        with pytest.raises(ValidationError):
            SearchQuery(query="iphone", limit=0)

    def test_rejects_limit_over_max(self) -> None:
        with pytest.raises(ValidationError):
            SearchQuery(query="iphone", limit=101)


class TestListing:
    def test_minimal_has_optional_price(self) -> None:
        item = Listing(id=1, title="iPhone 15")
        assert item.price is None
        assert item.params == {}

    def test_full(self) -> None:
        item = Listing(
            id=1234567890,
            title="iPhone 15 128GB",
            price=65000.0,
            url="https://www.avito.ru/moskva/telefony/x_1234567890",
            region="Москва",
            params={"Память": "128 ГБ"},
        )
        assert item.price == 65000.0
        assert item.params["Память"] == "128 ГБ"


class TestSearchResult:
    def test_count_is_derived_from_items(self) -> None:
        res = SearchResult(items=[Listing(id=1, title="a"), Listing(id=2, title="b")])
        assert res.count == 2

    def test_empty_result(self) -> None:
        res = SearchResult(items=[])
        assert res.count == 0


class TestOwnItem:
    def test_minimal_needs_only_id(self) -> None:
        item = OwnItem(id=42)
        assert item.title is None
        assert item.status is None
        assert item.price is None

    def test_ignores_unknown_api_fields(self) -> None:
        item = OwnItem.model_validate(
            {"id": 42, "status": "active", "unexpected": {"x": 1}}
        )
        assert item.status == "active"

    def test_requires_id(self) -> None:
        with pytest.raises(ValidationError):
            OwnItem.model_validate({"title": "нет id"})


class TestOwnItemsResult:
    def test_count_is_derived(self) -> None:
        res = OwnItemsResult(items=[OwnItem(id=1), OwnItem(id=2)])
        assert res.count == 2

    def test_empty(self) -> None:
        assert OwnItemsResult(items=[]).count == 0


class TestAccountInfo:
    def test_id_required_name_optional(self) -> None:
        acc = AccountInfo(id=777)
        assert acc.id == 777
        assert acc.name is None

    def test_ignores_extra_personal_fields(self) -> None:
        acc = AccountInfo.model_validate(
            {"id": 777, "name": "Магазин", "email": "x@y.z", "phone": "+7999"}
        )
        assert acc.name == "Магазин"
        assert not hasattr(acc, "phone")
