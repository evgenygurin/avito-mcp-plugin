"""Тесты движка извлечения: find_json_on_page / classify / extract_facts."""

from pathlib import Path

from avito_mcp_server.parser import (
    classify,
    extract_facts,
    find_json_on_page,
    next_page_url,
    parse_listing_detail,
)

FIX = Path(__file__).parent / "fixtures"


def test_find_json_catalog() -> None:
    html = (FIX / "catalog.html").read_text(encoding="utf-8")
    data = find_json_on_page(html)
    assert "catalog" in data
    assert len(data["catalog"]["items"]) == 3


def test_classify_redirect_on_real_stub() -> None:
    # redirect_stub.html — реальная страница Avito (html-escaped JSON): проверяет
    # и unescape, и детекцию SSR-редиректа на канонический URL.
    html = (FIX / "redirect_stub.html").read_text(encoding="utf-8")
    kind, payload = classify(html)
    assert kind == "redirect"
    assert isinstance(payload, str) and payload.startswith("/")


def test_classify_ok_and_extract_facts() -> None:
    html = (FIX / "catalog.html").read_text(encoding="utf-8")
    kind, catalog = classify(html)
    assert kind == "ok"

    facts = extract_facts(catalog)
    # Третий item (id=0, баннер) отсеивается — нет валидного id.
    assert len(facts) == 2

    first = facts[0]
    assert first.id == 7890298070
    assert first.price == 98630444
    assert first.address == "Нижний Новгород"
    # urlPath уже с ведущим слэшем — склейка без лишнего "/".
    assert first.url == "https://www.avito.ru/nizhniy_novgorod/kvartiry/x_7890298070"
    assert first.is_promotion is True
    assert first.seller_id == "brand-x"
    assert first.published_at == 1700000000

    second = facts[1]
    assert second.is_promotion is False
    assert second.seller_id is None


def test_next_page_url_from_pager() -> None:
    # Каталог сам несёт ссылки на страницы — свой сборщик API-параметров не нужен.
    catalog = {
        "items": [],
        "pager": {"next": "/nizhniy_novgorod/kvartiry/sdam-ASgB?p=2", "current": 1},
    }
    assert (
        next_page_url(catalog)
        == "https://www.avito.ru/nizhniy_novgorod/kvartiry/sdam-ASgB?p=2"
    )


def test_next_page_url_absent_on_last_page() -> None:
    assert next_page_url({"items": [], "pager": {"current": 34}}) is None
    assert next_page_url({"items": []}) is None


def test_classify_firewall_block() -> None:
    # Реальная страница Avito при выжженном IP: HTTP 429 + firewall с капчей.
    # Отличается от nojson: причина известна, ретраи без смены IP бесполезны.
    html = (FIX / "firewall_block.html").read_text(encoding="utf-8")
    kind, payload = classify(html)
    assert kind == "firewall"
    assert payload is None


def test_address_prefers_street_and_district() -> None:
    # Реальная выдача каталога: улица с домом лежит в geo.formattedAddress, а
    # район/метро — в geo.geoReferences. locationName даёт только город, по нему
    # нельзя отфильтровать район (geo-фильтр тулзы).
    catalog = {
        "items": [
            {
                "id": 1,
                "title": "1-к. квартира",
                "addressDetailed": {"locationName": "Нижний Новгород"},
                "geo": {
                    "formattedAddress": "Ул. Бетанкура, 7",
                    "geoReferences": [
                        {"content": "Стрелка"},
                        {"content": "р-н Канавинский"},
                    ],
                },
            }
        ]
    }
    (listing,) = extract_facts(catalog)
    assert listing.address == "Ул. Бетанкура, 7, Стрелка, р-н Канавинский"


def test_address_falls_back_to_city() -> None:
    catalog = {
        "items": [
            {"id": 2, "title": "2-к. квартира", "location": {"name": "Дзержинск"}}
        ]
    }
    (listing,) = extract_facts(catalog)
    assert listing.address == "Дзержинск"


def test_classify_nojson_on_blank() -> None:
    kind, payload = classify("<html><body>no state here</body></html>")
    assert kind == "nojson"
    assert payload is None


def test_parse_listing_detail() -> None:
    html = (FIX / "listing_detail.html").read_text(encoding="utf-8")
    listing = parse_listing_detail(html, with_views=True)
    assert listing is not None
    assert listing.id == 7890298070
    assert listing.title == "1-к. квартира, 45 м², 5/9 эт."
    assert listing.price == 5500000
    assert listing.address == "Нижний Новгород"
    assert (
        listing.description
        == "Продаётся отличная квартира в центре города. Рядом метро."
    )
    assert listing.views == 1234
    assert listing.params == {
        "Площадь": "45 м²",
        "Этаж": "5 из 9",
        "Тип дома": "кирпичный",
    }


def test_parse_listing_detail_no_views() -> None:
    html = (FIX / "listing_detail.html").read_text(encoding="utf-8")
    listing = parse_listing_detail(html, with_views=False)
    assert listing is not None
    assert listing.views is None


def test_parse_listing_detail_no_item_returns_none() -> None:
    listing = parse_listing_detail("<html><body>no state</body></html>")
    assert listing is None


def test_published_at_normalized_to_seconds() -> None:
    # Avito отдаёт sortTimeStamp в миллисекундах, но встречаются и секунды.
    # Наружу модель должна отдавать ОДНУ единицу — epoch-секунды, иначе фильтр
    # max_age промахивается на три порядка.
    ms = extract_facts({"items": [{"id": 1, "title": "x", "sortTimeStamp": 1783756196000}]})
    assert ms[0].published_at == 1783756196

    sec = extract_facts({"items": [{"id": 2, "title": "x", "sortTimeStamp": 1700000000}]})
    assert sec[0].published_at == 1700000000
