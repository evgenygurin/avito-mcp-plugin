"""Интеграционные тесты серверного инстанса (регистрация тулз)."""

from fastmcp import Client

from avito_mcp_server.server import mcp


async def test_tool_annotations_match_side_effects() -> None:
    # Context7-аудит (fastmcp 3.4.4): без аннотаций MCP-клиенты, чтящие хинты,
    # просят подтверждение даже у чистых чтений (болезненно для пагинации), а
    # реально деструктивные тулзы (запись файла, необратимое сообщение
    # третьим лицам) не несут никакого сигнала.
    read_only = {
        "search_listings",
        "get_listing",
        "check_proxy_health",
        "scan_new_listings",
        "get_price_history",
    }
    destructive = {"export_listings", "send_notification"}

    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}

    for name in read_only:
        annotations = tools[name].annotations
        assert annotations is not None, f"{name}: нет аннотаций"
        assert annotations.readOnlyHint is True, f"{name}: readOnlyHint"

    for name in destructive:
        annotations = tools[name].annotations
        assert annotations is not None, f"{name}: нет аннотаций"
        assert annotations.destructiveHint is True, f"{name}: destructiveHint"


async def test_network_tools_have_a_timeout() -> None:
    # Context7-аудит: worst-case rotate-until-clean — до AVITO_MAX_ROTATE_ATTEMPTS
    # (18) попыток с растущим backoff (до 60с потолка) НА СТРАНИЦУ, а
    # asyncio.to_thread не отменяем сам по себе — зависший скрап неотличим от
    # реального зависания сервера и жжёт proxy/spfa-бюджет впустую. Тулзовый
    # timeout (anyio.fail_after — подтверждено в исходниках fastmcp 3.4.4)
    # превращает это в ловимую ошибку клиента.
    for name in ("search_listings", "scan_new_listings", "get_listing"):
        tool = await mcp.get_tool(name)
        assert tool.timeout is not None and tool.timeout > 0, name

    proxy_tool = await mcp.get_tool("check_proxy_health")
    assert proxy_tool.timeout is not None and proxy_tool.timeout > 0


async def test_server_instantiates_and_serves_skills() -> None:
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
        # Парсинг-тулзы зарегистрированы.
        assert {
            "search_listings",
            "check_proxy_health",
            "get_listing",
            "scan_new_listings",
            "get_price_history",
            "export_listings",
            "send_notification",
        } <= names
        # Удалённых тулз официального API нет.
        assert names.isdisjoint(
            {"ping", "official_api_call", "get_own_items", "get_account_info"}
        )
        resources = await client.list_resources()
        assert any(str(r.uri).startswith("skill://") for r in resources)
