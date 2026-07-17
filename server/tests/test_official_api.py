"""Тесты клиента официального API (httpx.MockTransport — мок только границы сети)."""

from collections.abc import Callable

import httpx
import pytest

from avito_mcp_server.official_api import (
    AvitoOfficialClient,
    AvitoOfficialConfig,
    validate_endpoint,
)


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> AvitoOfficialClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = AvitoOfficialConfig(client_id="cid", client_secret="secret")
    return AvitoOfficialClient(config, http)


class TestGetToken:
    async def test_posts_client_credentials_and_returns_token(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["body"] = request.content.decode()
            return httpx.Response(
                200, json={"access_token": "TOKEN", "expires_in": 86400}
            )

        token = await make_client(handler).get_token()

        assert token == "TOKEN"
        assert seen["path"] == "/token/"
        assert "grant_type=client_credentials" in seen["body"]
        assert "client_id=cid" in seen["body"]

    async def test_token_is_cached_across_calls(self) -> None:
        calls = {"token": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token/":
                calls["token"] += 1
            return httpx.Response(200, json={"access_token": "TOKEN"})

        client = make_client(handler)
        await client.get_token()
        await client.get_token()

        assert calls["token"] == 1


class TestCall:
    async def test_sends_bearer_and_returns_json(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token/":
                return httpx.Response(200, json={"access_token": "TOKEN"})
            seen["auth"] = request.headers.get("Authorization", "")
            seen["path"] = request.url.path
            return httpx.Response(200, json={"result": [1, 2, 3]})

        data = await make_client(handler).call("GET", "core/v1/items")

        assert seen["auth"] == "Bearer TOKEN"
        assert seen["path"] == "/core/v1/items"
        assert data == {"result": [1, 2, 3]}

    async def test_raises_on_http_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token/":
                return httpx.Response(200, json={"access_token": "TOKEN"})
            return httpx.Response(403, json={"error": "forbidden"})

        with pytest.raises(httpx.HTTPStatusError):
            await make_client(handler).call("GET", "core/v1/items")

    async def test_rejects_disallowed_endpoint_before_network(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token/":
                return httpx.Response(200, json={"access_token": "TOKEN"})
            raise AssertionError("сеть не должна вызываться при запрете эндпоинта")

        with pytest.raises(ValueError):
            await make_client(handler).call("GET", "evil/v1/steal")


class TestValidateEndpoint:
    def test_allows_own_data_namespace(self) -> None:
        validate_endpoint("GET", "core/v1/items")
        validate_endpoint("GET", "/core/v1/accounts/self")
        validate_endpoint("POST", "messenger/v1/accounts/1/chats")

    def test_rejects_unknown_namespace(self) -> None:
        with pytest.raises(ValueError):
            validate_endpoint("GET", "search/v1/items")

    def test_rejects_absolute_url(self) -> None:
        with pytest.raises(ValueError):
            validate_endpoint("GET", "https://evil.example/core/v1/items")

    def test_rejects_path_traversal(self) -> None:
        with pytest.raises(ValueError):
            validate_endpoint("GET", "core/v1/../../secret")

    def test_rejects_unsupported_method(self) -> None:
        with pytest.raises(ValueError):
            validate_endpoint("TRACE", "core/v1/items")


class TestAclose:
    async def test_closes_underlying_http(self) -> None:
        http = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))
        )
        client = AvitoOfficialClient(
            AvitoOfficialConfig(client_id="c", client_secret="s"), http
        )
        await client.aclose()
        assert http.is_closed


class TestConfigFromEnv:
    def test_raises_without_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AVITO_CLIENT_ID", raising=False)
        monkeypatch.delenv("AVITO_CLIENT_SECRET", raising=False)
        with pytest.raises(ValueError):
            AvitoOfficialConfig.from_env()

    def test_reads_values_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AVITO_CLIENT_ID", "x")
        monkeypatch.setenv("AVITO_CLIENT_SECRET", "y")
        cfg = AvitoOfficialConfig.from_env()
        assert cfg.client_id == "x"
        assert cfg.client_secret == "y"
