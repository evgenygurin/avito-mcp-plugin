"""Тесты тулзы export_listings (in-memory Client)."""

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

import avito_mcp_server.tools.exporting as exp_mod


def _mcp() -> FastMCP:
    m = FastMCP("test")
    exp_mod.register(m)
    return m


async def test_export_listings_json_in_memory() -> None:
    items = [
        {"id": 1, "title": "квартира", "price": 5000000, "address": "NN"},
        {"id": 2, "title": "гараж", "price": 900000, "address": "NN"},
    ]
    async with Client(_mcp()) as client:
        res = await client.call_tool("export_listings", {"items": items, "fmt": "json"})

    assert res.data.count == 2
    assert res.data.format == "json"
    assert res.data.path is None
    assert "квартира" in res.data.content
    assert "5000000" in res.data.content


async def test_export_listings_xlsx_to_base64() -> None:
    items = [{"id": 1, "title": "x", "price": 100}]
    async with Client(_mcp()) as client:
        res = await client.call_tool("export_listings", {"items": items, "fmt": "xlsx"})

    assert res.data.count == 1
    assert res.data.format == "xlsx"
    assert len(res.data.content) > 0
    import base64

    decoded = base64.b64decode(res.data.content)
    assert len(decoded) > 0


async def test_input_schema_describes_listing_shape() -> None:
    # Context7-аудит (fastmcp 3.4.4): items: list[dict[str, object]] давал
    # схему с additionalProperties=true — модель не видит ни полей, ни типов
    # Listing, ошибка формы всплывает поздно как ToolError из тела вместо
    # отбоя на границе валидации аргументов.
    async with Client(_mcp()) as client:
        tools = await client.list_tools()
    export_tool = next(t for t in tools if t.name == "export_listings")
    items_schema = export_tool.inputSchema["properties"]["items"]
    item_schema = items_schema["items"]
    # dict[str, object] даёт {"type": "object"} без ссылки на Listing и без
    # required — вложенная схема Listing обязана нести хотя бы "id"/"title".
    resolved = item_schema
    if "$ref" in resolved:
        ref_name = resolved["$ref"].rsplit("/", 1)[-1]
        resolved = export_tool.inputSchema["$defs"][ref_name]
    assert "id" in resolved["properties"]
    assert "title" in resolved["properties"]


async def test_fmt_schema_is_enum_not_free_string() -> None:
    # Context7-аудит: fmt как голый str не несёт enum — легальный набор
    # (xlsx|json|csv) не доходит до модели, а "excel"/"xls" жжёт круг вызова
    # на ToolError вместо отбоя на границе аргументов.
    async with Client(_mcp()) as client:
        tools = await client.list_tools()
    export_tool = next(t for t in tools if t.name == "export_listings")
    fmt_schema = export_tool.inputSchema["properties"]["fmt"]
    assert set(fmt_schema.get("enum", [])) == {"xlsx", "json", "csv"}


async def test_missing_required_field_rejected_at_argument_boundary() -> None:
    async with Client(_mcp()) as client:
        with pytest.raises(ToolError):
            await client.call_tool(
                "export_listings", {"items": [{"title": "без id"}], "fmt": "json"}
            )
