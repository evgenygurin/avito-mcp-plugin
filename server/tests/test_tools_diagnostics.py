"""Тесты тулзы check_proxy_health (in-memory Client, мок движка)."""

import json

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

import avito_mcp_server.tools.diagnostics as diag_mod
from avito_mcp_server.proxies.proxy import NoProxy


class _FakeClient:
    proxy = NoProxy()
    cookies = None


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


async def test_check_proxy_health_wraps_setup_errors_in_tool_error(
    monkeypatch,
) -> None:
    # build_http_client() может бросить ValueError("пул прокси пуст") ДО
    # входа в try/except _probe — эта ветка была единственной среди 7 тулз
    # без общей ToolError-границы, отдавая сырое исключение вместо контракта.
    def _boom():
        raise ValueError("пул прокси пуст")

    monkeypatch.setattr(diag_mod, "build_http_client", _boom)

    async with Client(_mcp()) as client:
        with pytest.raises(ToolError, match="пул прокси пуст"):
            await client.call_tool("check_proxy_health", {})


async def test_check_proxy_health_reports_block(monkeypatch) -> None:
    monkeypatch.setattr(diag_mod, "build_http_client", lambda: _FakeClient())
    monkeypatch.setattr(diag_mod, "fetch_catalog", lambda c, u: ("softblock", None))

    async with Client(_mcp()) as client:
        res = await client.call_tool("check_proxy_health", {})

    assert res.data.ok is False
    assert "softblock" in res.data.detail


async def test_check_proxy_health_explains_firewall(monkeypatch) -> None:
    # Диагностика должна называть причину и следующий шаг, а не только код статуса.
    monkeypatch.setattr(diag_mod, "build_http_client", lambda: _FakeClient())
    monkeypatch.setattr(diag_mod, "fetch_catalog", lambda c, u: ("firewall", None))

    async with Client(_mcp()) as client:
        res = await client.call_tool("check_proxy_health", {})

    assert res.data.ok is False
    assert "AVITO_PROXY" in res.data.detail


async def test_check_proxy_health_probes_whole_pool(monkeypatch) -> None:
    # С пулом надо знать, какие адреса живые, а не только итог по первому.
    from avito_mcp_server.proxies.proxy import ProxyPool

    pool = ProxyPool(["user:secret@h1:1", "user:secret@h2:2"])

    class _Client:
        proxy = pool
        cookies = None

    def _fetch(client, url):
        # Первый адрес выжжен, второй чистый.
        current = client.proxy.httpx_proxy()
        return ("ok", {"items": [1]}) if "h2" in current else ("firewall", None)

    monkeypatch.setattr(diag_mod, "build_http_client", _Client)
    monkeypatch.setattr(diag_mod, "fetch_catalog", _fetch)

    async with Client(_mcp()) as client:
        res = await client.call_tool("check_proxy_health", {})

    assert [p.proxy for p in res.data.probes] == ["h1:1", "h2:2"]
    assert [p.ok for p in res.data.probes] == [False, True]
    # Пароль не должен утечь в вывод тулзы.
    assert "secret" not in json.dumps(res.structured_content, ensure_ascii=False)
    # Хотя бы один живой адрес — связка рабочая.
    assert res.data.ok is True


async def test_probe_verdicts_stick_to_their_own_proxy(monkeypatch) -> None:
    # Реальный HttpClient при блокировке ротирует прокси ВНУТРИ запроса и может
    # вернуть успех уже с другого адреса. Если проба идёт через общий пул, этот
    # успех припишется мёртвому адресу — диагностика соврёт там, где ей верят.
    from avito_mcp_server.proxies.proxy import ProxyPool

    pool = ProxyPool(["dead:1", "alive:2"])

    class _Client:
        proxy = pool
        cookies = None

    def _fetch(client, url):
        # rotate-until-clean с ограничением попыток: на статическом прокси
        # ротация ничего не меняет, на пуле — переключит на живой адрес.
        for _ in range(3):
            if "dead" not in (client.proxy.httpx_proxy() or ""):
                return ("ok", {"items": [1]})
            client.proxy.rotate()
        return ("firewall", None)

    monkeypatch.setattr(diag_mod, "build_http_client", _Client)
    monkeypatch.setattr(diag_mod, "fetch_catalog", _fetch)

    async with Client(_mcp()) as client:
        res = await client.call_tool("check_proxy_health", {})

    verdicts = {p.proxy: p.ok for p in res.data.probes}
    assert verdicts["dead:1"] is False, "мёртвый адрес не может быть живым"
    assert verdicts["alive:2"] is True
