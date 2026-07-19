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


def test_every_spec_field_actually_filters() -> None:
    """Каждое поле FilterSpec обязано влиять на выдачу.

    Критерий, забытый в ``_CRITERIA``, — это молча неработающий параметр тулзы:
    агент задаёт фильтр, получает полный список и не узнаёт, что его проигнорировали.
    """
    item = _l(
        1, title="гараж", price=500, seller="bad", address="Москва", published_at=0
    )
    rejecting = {
        "include_keywords": FilterSpec(include_keywords=["квартира"]),
        "exclude_keywords": FilterSpec(exclude_keywords=["гараж"]),
        "seller_blacklist": FilterSpec(seller_blacklist=["bad"]),
        "price_min": FilterSpec(price_min=1000),
        "price_max": FilterSpec(price_max=100),
        "geo": FilterSpec(geo="Казань"),
        "max_age": FilterSpec(max_age=60),
    }
    assert set(rejecting) == set(FilterSpec.model_fields), "поле спеки без критерия"
    for field, spec in rejecting.items():
        assert apply_filters([item], spec, now=1_000_000.0) == [], field


def test_listing_without_price_fails_range_filter() -> None:
    # Объявление без цены не может доказать попадание в диапазон — иначе
    # «до 1 млн» вернуло бы объявления «цена по запросу».
    items = [_l(1, price=None), _l(2, price=500)]
    assert [i.id for i in apply_filters(items, FilterSpec(price_max=1000))] == [2]
