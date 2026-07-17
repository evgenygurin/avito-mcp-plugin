"""Тесты MCP-тулзы official_api_call (in-memory Client + мок фабрики клиента)."""

from collections.abc import Callable

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from avito_mcp_server.official_api import AvitoOfficialClient, AvitoOfficialConfig
from avito_mcp_server.tools import official_api as tool_mod


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


class TestOfficialApiCallTool:
    async def test_returns_api_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token/":
                return httpx.Response(200, json={"access_token": "T"})
            return httpx.Response(200, json={"result": {"id": 1}})

        monkeypatch.setattr(tool_mod, "build_client", fake_factory(handler))
        async with Client(build_mcp()) as client:
            res = await client.call_tool(
                "official_api_call", {"method": "GET", "path": "core/v1/items"}
            )
            assert res.data == {"result": {"id": 1}}

    async def test_missing_credentials_raises_toolerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AVITO_CLIENT_ID", raising=False)
        monkeypatch.delenv("AVITO_CLIENT_SECRET", raising=False)
        async with Client(build_mcp()) as client:
            with pytest.raises(ToolError):
                await client.call_tool(
                    "official_api_call", {"method": "GET", "path": "x"}
                )

    async def test_http_error_raises_toolerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token/":
                return httpx.Response(200, json={"access_token": "T"})
            return httpx.Response(403, json={"error": "forbidden"})

        monkeypatch.setattr(tool_mod, "build_client", fake_factory(handler))
        async with Client(build_mcp()) as client:
            with pytest.raises(ToolError):
                await client.call_tool(
                    "official_api_call", {"method": "GET", "path": "x"}
                )
