"""Тесты утилит (детерминированные, без сети)."""

import pytest

from avito_mcp_server.utils import extract_listing_id


class TestExtractListingId:
    def test_extracts_id_from_desktop_url(self) -> None:
        url = "https://www.avito.ru/moskva/telefony/iphone_15_128gb_1234567890"
        assert extract_listing_id(url) == 1234567890

    def test_extracts_id_from_mobile_api_url(self) -> None:
        url = "https://m.avito.ru/api/15/items/9876543210"
        assert extract_listing_id(url) == 9876543210

    def test_extracts_id_from_url_with_query_string(self) -> None:
        url = "https://www.avito.ru/moskva/avtomobili/bmw_x5_5555555555?context=abc"
        assert extract_listing_id(url) == 5555555555

    def test_accepts_bare_numeric_id(self) -> None:
        assert extract_listing_id("1234567890") == 1234567890

    def test_raises_on_url_without_id(self) -> None:
        with pytest.raises(ValueError):
            extract_listing_id("https://www.avito.ru/moskva/telefony")

    def test_raises_on_empty_string(self) -> None:
        with pytest.raises(ValueError):
            extract_listing_id("")
