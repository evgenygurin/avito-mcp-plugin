"""Тесты утилит (детерминированные, без сети)."""

import pytest

from avito_mcp_server.utils import (
    extract_listing_id,
    to_absolute_avito_url,
    to_listing_url,
)


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


class TestToListingUrl:
    """Единый разбор пользовательского ввода get_listing (URL либо id)."""

    def test_keeps_listing_url_as_is(self) -> None:
        url = "https://www.avito.ru/moskva/telefony/iphone_1234567890"
        assert to_listing_url(url) == url

    def test_builds_canonical_url_from_bare_id(self) -> None:
        assert to_listing_url("1234567890") == "https://www.avito.ru/items/1234567890"

    def test_raises_on_garbage(self) -> None:
        with pytest.raises(ValueError):
            to_listing_url("не-id")


class TestToAbsoluteAvitoUrl:
    def test_prefixes_relative_path_with_domain(self) -> None:
        assert (
            to_absolute_avito_url("/moskva/telefony?p=2")
            == "https://www.avito.ru/moskva/telefony?p=2"
        )

    def test_leaves_absolute_url_untouched(self) -> None:
        url = "https://www.avito.ru/moskva/telefony-ASgBAg?localPriority=0"
        assert to_absolute_avito_url(url) == url

    def test_leaves_other_scheme_untouched(self) -> None:
        # На случай нестандартных редиректов — не подменяем произвольный http(s) URL.
        assert to_absolute_avito_url("http://example.com/x") == "http://example.com/x"
