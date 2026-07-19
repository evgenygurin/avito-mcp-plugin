"""Тесты тулзы search_listings (in-memory Client, мок сетевой границы)."""

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

import avito_mcp_server.tools.catalog as catalog_mod
import avito_mcp_server.tools.search as search_mod

CATALOG = {
    "items": [
        {
            "id": 1,
            "title": "1-к квартира",
            "priceDetailed": {"value": 5000000},
            "location": {"name": "Нижний Новгород"},
            "urlPath": "/x_1",
        },
        {
            "id": 2,
            "title": "гараж",
            "priceDetailed": {"value": 900000},
            "location": {"name": "Нижний Новгород"},
            "urlPath": "/x_2",
        },
    ]
}


def _mcp() -> FastMCP:
    m = FastMCP("test")
    search_mod.register(m)
    return m


async def test_search_listings_returns_filtered(monkeypatch) -> None:
    monkeypatch.setattr(catalog_mod, "page_pause", lambda: 0.0)
    monkeypatch.setattr(catalog_mod, "build_http_client", lambda: object())
    monkeypatch.setattr(
        catalog_mod, "fetch_catalog", lambda client, url: ("ok", CATALOG)
    )

    async with Client(_mcp()) as client:
        res = await client.call_tool(
            "search_listings",
            {
                "url": "https://www.avito.ru/nn/kvartiry",
                "include_keywords": ["квартира"],
            },
        )

    assert res.data.count == 1
    assert res.data.items[0].id == 1
    assert res.data.items[0].url == "https://www.avito.ru/x_1"


async def test_search_listings_walks_pages(monkeypatch) -> None:
    # pages=2 → идём по pager.next; объявления страниц склеиваются.
    page1 = {
        "items": [dict(CATALOG["items"][0])],
        "pager": {"next": "/nn/kvartiry?p=2", "current": 1},
    }
    page2 = {"items": [dict(CATALOG["items"][1])], "pager": {"current": 2}}
    seen: list[str] = []

    def _fetch(client, url):
        seen.append(url)
        return ("ok", page1 if len(seen) == 1 else page2)

    monkeypatch.setattr(catalog_mod, "page_pause", lambda: 0.0)
    monkeypatch.setattr(catalog_mod, "build_http_client", lambda: object())
    monkeypatch.setattr(catalog_mod, "fetch_catalog", _fetch)

    async with Client(_mcp()) as client:
        res = await client.call_tool(
            "search_listings", {"url": "https://www.avito.ru/nn/kvartiry", "pages": 2}
        )

    assert seen == [
        "https://www.avito.ru/nn/kvartiry",
        "https://www.avito.ru/nn/kvartiry?p=2",
    ]
    assert res.data.count == 2
    assert [i.id for i in res.data.items] == [1, 2]


async def test_search_listings_stops_on_last_page(monkeypatch) -> None:
    # Запрошено больше страниц, чем есть: без pager.next обход прекращается,
    # лишних запросов не делаем и ошибку не бросаем.
    calls: list[str] = []

    def _fetch(client, url):
        calls.append(url)
        return ("ok", {"items": [dict(CATALOG["items"][0])], "pager": {"current": 1}})

    monkeypatch.setattr(catalog_mod, "page_pause", lambda: 0.0)
    monkeypatch.setattr(catalog_mod, "build_http_client", lambda: object())
    monkeypatch.setattr(catalog_mod, "fetch_catalog", _fetch)

    async with Client(_mcp()) as client:
        res = await client.call_tool(
            "search_listings", {"url": "https://www.avito.ru/nn/kvartiry", "pages": 5}
        )

    assert len(calls) == 1
    assert res.data.count == 1


async def test_search_listings_dedupes_across_pages(monkeypatch) -> None:
    # Каталог сдвигается между запросами — одно объявление приходит дважды.
    page = {
        "items": [dict(CATALOG["items"][0])],
        "pager": {"next": "/nn/kvartiry?p=2", "current": 1},
    }
    monkeypatch.setattr(catalog_mod, "page_pause", lambda: 0.0)
    monkeypatch.setattr(catalog_mod, "build_http_client", lambda: object())
    monkeypatch.setattr(catalog_mod, "fetch_catalog", lambda client, url: ("ok", page))

    async with Client(_mcp()) as client:
        res = await client.call_tool(
            "search_listings", {"url": "https://www.avito.ru/nn/kvartiry", "pages": 3}
        )

    assert res.data.count == 1


async def test_search_listings_explains_firewall(monkeypatch) -> None:
    # При выжженном IP агент должен получить действие («нужен чистый RU-прокси»),
    # а не сырой код статуса: ретраи без смены IP тут бесполезны.
    monkeypatch.setattr(catalog_mod, "page_pause", lambda: 0.0)
    monkeypatch.setattr(catalog_mod, "build_http_client", lambda: object())
    monkeypatch.setattr(
        catalog_mod, "fetch_catalog", lambda client, url: ("firewall", None)
    )

    async with Client(_mcp()) as client:
        with pytest.raises(ToolError) as exc:
            await client.call_tool(
                "search_listings", {"url": "https://www.avito.ru/nn"}
            )

    message = str(exc.value)
    assert "IP" in message
    assert "AVITO_PROXY" in message


async def test_search_listings_errors_on_non_ok(monkeypatch) -> None:
    monkeypatch.setattr(catalog_mod, "page_pause", lambda: 0.0)
    monkeypatch.setattr(catalog_mod, "build_http_client", lambda: object())
    monkeypatch.setattr(
        catalog_mod, "fetch_catalog", lambda client, url: ("softblock", None)
    )

    async with Client(_mcp()) as client:
        with pytest.raises(ToolError):
            await client.call_tool(
                "search_listings", {"url": "https://www.avito.ru/nn"}
            )


async def test_pages_schema_has_sane_bounds() -> None:
    # Context7-аудит: каждая страница — до 18 ротаций IP + платные spfa-куки.
    # Ошибочный pages=500 от модели уходит в многочасовой прогон, неотличимый
    # от зависания — граница должна отбивать это на уровне схемы аргументов.
    async with Client(_mcp()) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "search_listings")
    pages_schema = tool.inputSchema["properties"]["pages"]
    assert pages_schema.get("minimum") == 1
    assert pages_schema.get("maximum") is not None


async def test_pages_out_of_bounds_rejected_at_argument_boundary(
    monkeypatch,
) -> None:
    monkeypatch.setattr(catalog_mod, "page_pause", lambda: 0.0)
    monkeypatch.setattr(catalog_mod, "build_http_client", lambda: object())
    monkeypatch.setattr(
        catalog_mod, "fetch_catalog", lambda client, url: ("ok", CATALOG)
    )

    async with Client(_mcp()) as client:
        with pytest.raises(ToolError):
            await client.call_tool(
                "search_listings", {"url": "https://www.avito.ru/nn", "pages": 500}
            )


async def test_max_age_has_parameter_description() -> None:
    # Context7-аудит: ни один из 9 параметров не нёс description — max_age
    # голый integer без единицы, модель, читающая только прозу докстринга
    # вольно, могла прислать дни/timestamp вместо секунд, и фильтр молча
    # исключил бы всё без единой ошибки.
    async with Client(_mcp()) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "search_listings")
    max_age_schema = tool.inputSchema["properties"]["max_age"]
    assert "секунд" in max_age_schema.get("description", "").lower()
