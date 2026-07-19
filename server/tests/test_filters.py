"""Тесты фильтров: keyword/seller/price/geo/max_age."""

from avito_mcp_server.filters.filters import FilterSpec, apply_filters
from avito_mcp_server.models import Listing


def _l(
    id: int,
    title: str = "a",
    price: float | None = 1.0,
    seller: str | None = "s",
    address: str | None = None,
    published_at: int | None = None,
) -> Listing:
    return Listing(
        id=id,
        title=title,
        price=price,
        seller_id=seller,
        address=address,
        published_at=published_at,
    )


def test_empty_spec_passes_all() -> None:
    items = [_l(1), _l(2)]
    assert len(apply_filters(items, FilterSpec())) == 2


def test_price_and_keyword_filters() -> None:
    items = [
        _l(1, "1-к квартира", 5_000_000),
        _l(2, "гараж", 900_000),
        _l(3, "2-к квартира студия", 12_000_000),
    ]
    spec = FilterSpec(
        include_keywords=["квартира"],
        exclude_keywords=["студия"],
        price_min=1_000_000,
        price_max=10_000_000,
    )
    assert [i.id for i in apply_filters(items, spec)] == [1]


def test_seller_blacklist() -> None:
    items = [_l(1, seller="bad"), _l(2, seller="ok")]
    assert [
        i.id for i in apply_filters(items, FilterSpec(seller_blacklist=["bad"]))
    ] == [2]


def test_geo_substring() -> None:
    items = [_l(1, address="Нижний Новгород, Автозаводский"), _l(2, address="Москва")]
    assert [i.id for i in apply_filters(items, FilterSpec(geo="Автозаводский"))] == [1]


def test_max_age_with_injected_now() -> None:
    # published_at приходит в epoch-СЕКУНДАХ: миллисекунды Avito приводит к ним
    # parser._published_at, так что фильтр работает в одной шкале с `now`.
    now = 1_000_000.0
    recent = int(now - 100)  # 100 с назад
    old = int(now - 100_000)  # ~28 ч назад
    items = [_l(1, published_at=recent), _l(2, published_at=old)]
    out = apply_filters(items, FilterSpec(max_age=3600), now=now)
    assert [i.id for i in out] == [1]
