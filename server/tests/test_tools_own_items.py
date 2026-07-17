"""Тесты типобезопасных тулз своего кабинета (get_own_items, get_account_info).

In-memory Client(mcp); сетевая граница — httpx.MockTransport; фабрика клиента
подменяется monkeypatch (как в test_tools_official_api).
"""

from collections.abc import Callable

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from avito_mcp_server.official_api import AvitoOfficialClient, AvitoOfficialConfig
from avito_mcp_server.tools import own_items as tool_mod


def build_mcp() -> FastMCP:
    mcp: FastMCP = FastMCP("test")
    tool_mod.register(mcp)
    return mcp


def fake_factory(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[[], AvitoOfficialClient]:
    def _factory() -> AvitoOfficialClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        config = AvitoOfficialConfig(client_id="c", client_secret="s")
        return AvitoOfficialClient(config, http)

    return _factory


class TestGetOwnItems:
    async def test_maps_resources_to_structured_items(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token/":
                return httpx.Response(200, json={"access_token": "T"})
            return httpx.Response(
                200,
                json={
                    "resources": [
                        {
                            "id": 1,
                            "title": "iPhone 15",
                            "status": "active",
                            "price": 65000,
                            "category": {"id": 9, "name": "Телефоны"},
                            "url": "https://avito.ru/x_1",
                        }
                    ]
                },
            )

        monkeypatch.setattr(tool_mod, "build_client", fake_factory(handler))
        async with Client(build_mcp()) as client:
            res = await client.call_tool("get_own_items", {})
            assert res.data.count == 1
            item = res.data.items[0]
            assert item.id == 1
            assert item.title == "iPhone 15"
            assert item.status == "active"
            assert item.category == "Телефоны"

    async def test_empty_cabinet_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token/":
                return httpx.Response(200, json={"access_token": "T"})
            return httpx.Response(200, json={"resources": []})

        monkeypatch.setattr(tool_mod, "build_client", fake_factory(handler))
        async with Client(build_mcp()) as client:
            res = await client.call_tool("get_own_items", {})
            assert res.data.count == 0

    async def test_calls_items_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token/":
                return httpx.Response(200, json={"access_token": "T"})
            seen["path"] = request.url.path
            return httpx.Response(200, json={"resources": []})

        monkeypatch.setattr(tool_mod, "build_client", fake_factory(handler))
        async with Client(build_mcp()) as client:
            await client.call_tool("get_own_items", {})
        assert seen["path"] == "/core/v1/items"

    async def test_missing_credentials_raises_toolerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AVITO_CLIENT_ID", raising=False)
        monkeypatch.delenv("AVITO_CLIENT_SECRET", raising=False)
        async with Client(build_mcp()) as client:
            with pytest.raises(ToolError):
                await client.call_tool("get_own_items", {})


class TestGetAccountInfo:
    async def test_returns_id_and_name_dropping_personal_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token/":
                return httpx.Response(200, json={"access_token": "T"})
            return httpx.Response(
                200,
                json={
                    "id": 777,
                    "name": "Мой магазин",
                    "email": "seller@example.com",
                    "phone": "+79990000000",
                },
            )

        monkeypatch.setattr(tool_mod, "build_client", fake_factory(handler))
        async with Client(build_mcp()) as client:
            res = await client.call_tool("get_account_info", {})
            assert res.data.id == 777
            assert res.data.name == "Мой магазин"
            assert not hasattr(res.data, "email")

    async def test_calls_accounts_self_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token/":
                return httpx.Response(200, json={"access_token": "T"})
            seen["path"] = request.url.path
            return httpx.Response(200, json={"id": 1})

        monkeypatch.setattr(tool_mod, "build_client", fake_factory(handler))
        async with Client(build_mcp()) as client:
            await client.call_tool("get_account_info", {})
        assert seen["path"] == "/core/v1/accounts/self"
