"""Тесты сборки движка из переменных окружения."""

import pytest

import avito_mcp_server.config as config_mod
from avito_mcp_server.config import build_http_client, build_storage, page_pause
from avito_mcp_server.cookies.own import OwnCookiesProvider
from avito_mcp_server.cookies.spfa import SpfaCookiesProvider
from avito_mcp_server.proxies.proxy import MobileProxy, NoProxy, ProxyPool


def test_own_provider_and_mobile_proxy(monkeypatch) -> None:
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "own")
    monkeypatch.setenv("AVITO_OWN_COOKIES", '{"ft": "x"}')
    monkeypatch.setenv("AVITO_PROXY", "u:p@h:1")
    monkeypatch.setenv("AVITO_PROXY_CHANGE_URL", "https://chg?k=1")
    monkeypatch.setenv("AVITO_MAX_ROTATE_ATTEMPTS", "5")

    client = build_http_client()
    assert isinstance(client.cookies, OwnCookiesProvider)
    assert client.cookies.get() == {"ft": "x"}
    assert isinstance(client.proxy, MobileProxy)
    assert client.max_attempts == 5


def test_spfa_default_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("AVITO_COOKIE_PROVIDER", raising=False)
    monkeypatch.delenv("SPFA_API_KEY", raising=False)
    monkeypatch.delenv("AVITO_PROXY", raising=False)
    with pytest.raises(ValueError):
        build_http_client()


def test_spfa_with_key_no_proxy(monkeypatch) -> None:
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "spfa")
    monkeypatch.setenv("SPFA_API_KEY", "sk")
    monkeypatch.delenv("AVITO_PROXY", raising=False)
    monkeypatch.delenv("AVITO_PROXY_CHANGE_URL", raising=False)

    client = build_http_client()
    assert isinstance(client.cookies, SpfaCookiesProvider)
    assert isinstance(client.proxy, NoProxy)


def test_own_cookies_kv_format(monkeypatch) -> None:
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "own")
    monkeypatch.setenv("AVITO_OWN_COOKIES", "ft=1; foo=bar")
    monkeypatch.delenv("AVITO_PROXY", raising=False)

    client = build_http_client()
    assert isinstance(client.cookies, OwnCookiesProvider)
    assert client.cookies.get() == {"ft": "1", "foo": "bar"}


def test_build_storage_returns_supabase(monkeypatch) -> None:
    monkeypatch.setenv("AVITO_SUPABASE_DSN", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setattr(config_mod, "SupabaseStorage", lambda dsn: ("stub", dsn))
    assert build_storage() == ("stub", "postgresql://u:p@h:5432/postgres")


def test_build_storage_requires_dsn(monkeypatch) -> None:
    monkeypatch.delenv("AVITO_SUPABASE_DSN", raising=False)
    with pytest.raises(ValueError, match="AVITO_SUPABASE_DSN"):
        build_storage()


def test_page_pause_default(monkeypatch) -> None:
    # Пауза между страницами по умолчанию — многостраничный обход без неё
    # выжигает IP быстрее, чем успевает собрать данные.
    monkeypatch.delenv("AVITO_PAGE_PAUSE", raising=False)
    assert page_pause() == 1.0


def test_page_pause_from_env(monkeypatch) -> None:
    monkeypatch.setenv("AVITO_PAGE_PAUSE", "2.5")
    assert page_pause() == 2.5


def test_page_pause_ignores_garbage(monkeypatch) -> None:
    monkeypatch.setenv("AVITO_PAGE_PAUSE", "быстро")
    assert page_pause() == 1.0


def test_http_client_gets_cooldown_store_when_db_configured(monkeypatch) -> None:
    # Память о выжженных IP должна включаться сама, если БД уже настроена.
    monkeypatch.setenv("AVITO_PROXY", "h1:1,h2:2")
    monkeypatch.setenv("AVITO_SUPABASE_DSN", "postgresql://u:p@h:5432/postgres")
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "none")

    client = build_http_client()
    assert isinstance(client.proxy, ProxyPool)
    assert client.proxy.cooldown_store is not None


def test_http_client_works_without_db(monkeypatch) -> None:
    # Без AVITO_SUPABASE_DSN пул обязан работать — просто без памяти между запусками.
    monkeypatch.setenv("AVITO_PROXY", "h1:1,h2:2")
    monkeypatch.delenv("AVITO_SUPABASE_DSN", raising=False)
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "none")

    client = build_http_client()
    assert isinstance(client.proxy, ProxyPool)
    assert client.proxy.cooldown_store is None


def test_proxy_list_url_feeds_the_pool(monkeypatch) -> None:
    # Порты кабинета подхватываются сами — не нужно вести список руками в env.
    monkeypatch.setenv("AVITO_PROXY_LIST_URL", "https://api.example/list")
    monkeypatch.delenv("AVITO_PROXY", raising=False)
    monkeypatch.delenv("AVITO_SUPABASE_DSN", raising=False)
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "none")
    monkeypatch.setattr(
        config_mod, "fetch_proxy_list", lambda url: ["u:p@h1:1", "u:p@h2:2"]
    )

    client = build_http_client()
    assert isinstance(client.proxy, ProxyPool)
    assert client.proxy.urls == ["u:p@h1:1", "u:p@h2:2"]


def test_proxy_list_url_failure_falls_back_to_env(monkeypatch) -> None:
    # Кабинет недоступен — работаем на том, что задано вручную, а не падаем.
    monkeypatch.setenv("AVITO_PROXY_LIST_URL", "https://api.example/list")
    monkeypatch.setenv("AVITO_PROXY", "u:p@fallback:9")
    monkeypatch.delenv("AVITO_SUPABASE_DSN", raising=False)
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "none")
    monkeypatch.setattr(config_mod, "fetch_proxy_list", lambda url: [])

    client = build_http_client()
    assert client.proxy.httpx_proxy() == "http://u:p@fallback:9"


def test_default_rotate_attempts_bounds_worst_case(monkeypatch) -> None:
    # Дефолт задаёт худшее время ответа тулзы: сумма backoff
    # min(9*2^n, 60) по попыткам не должна уходить в четверть часа.
    monkeypatch.delenv("AVITO_MAX_ROTATE_ATTEMPTS", raising=False)
    monkeypatch.setenv("AVITO_COOKIE_PROVIDER", "none")
    monkeypatch.delenv("AVITO_PROXY", raising=False)
    monkeypatch.delenv("AVITO_PROXY_LIST_URL", raising=False)

    client = build_http_client()

    worst = sum(
        min(client.wait_after_rotate * 2**n, client.backoff_cap)
        for n in range(client.max_attempts - 1)
    )
    assert worst <= 150, f"худший случай {worst}с — тулза будет висеть"
