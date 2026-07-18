"""Тесты тулзы check_proxy_health (in-memory Client, мок движка)."""

from fastmcp import Client, FastMCP

import avito_mcp_server.tools.diagnostics as diag_mod
from avito_mcp_server.proxies.proxy import NoProxy


class _FakeClient:
    proxy = NoProxy()


def _mcp() -> FastMCP:
    m = FastMCP("test")
    diag_mod.register(m)
    return m


async def test_check_proxy_health_ok(monkeypatch) -> None:
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "own")
    monkeypatch.setattr(diag_mod, "build_http_client", lambda: _FakeClient())
    monkeypatch.setattr(diag_mod, "fetch_catalog", lambda c, u: ("ok", {"items": [1]}))

    async with Client(_mcp()) as client:
        res = await client.call_tool("check_proxy_health", {})

    assert res.data.ok is True
    assert res.data.cookie_provider == "own"
    assert res.data.proxy_type == "NoProxy"


async def test_check_proxy_health_reports_block(monkeypatch) -> None:
    monkeypatch.setattr(diag_mod, "build_http_client", lambda: _FakeClient())
    monkeypatch.setattr(diag_mod, "fetch_catalog", lambda c, u: ("softblock", None))

    async with Client(_mcp()) as client:
        res = await client.call_tool("check_proxy_health", {})

    assert res.data.ok is False
    assert "softblock" in res.data.detail
