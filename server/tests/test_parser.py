"""Тесты движка извлечения: find_json_on_page / classify / extract_facts."""

from pathlib import Path

from avito_mcp_server.parser import classify, extract_facts, find_json_on_page

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


def test_classify_nojson_on_blank() -> None:
    kind, payload = classify("<html><body>no state here</body></html>")
    assert kind == "nojson"
    assert payload is None
