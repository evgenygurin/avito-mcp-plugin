"""Тесты доменных Pydantic-моделей."""

import pytest
from pydantic import ValidationError

from avito_mcp_server.models import Listing, SearchQuery, SearchResult


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
