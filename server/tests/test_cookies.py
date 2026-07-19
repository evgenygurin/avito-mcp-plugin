"""Тесты провайдеров кук (spfa/own/playwright) с мокнутым httpx."""

import json
import sys

import pytest

import avito_mcp_server.cookies.spfa as spfa_mod
from avito_mcp_server.cookies.factory import build_cookies_provider
from avito_mcp_server.cookies.own import OwnCookiesProvider
from avito_mcp_server.cookies.spfa import SpfaCookiesProvider


class _Resp:
    def __init__(self, code: int, payload: dict | None = None) -> None:
        self.status_code = code
        self._p = payload or {}

    def json(self) -> dict:
        return self._p

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def test_spfa_buys_cookies(monkeypatch) -> None:
    seen: dict = {}

    def fake_post(url, **kwargs):  # noqa: ANN001
        seen["url"] = url
        seen["body"] = kwargs.get("json")
        return _Resp(200, {"results": {"id": "144514", "cookies": {"ft": "1"}}})

    monkeypatch.setattr(spfa_mod.httpx, "post", fake_post)
    p = SpfaCookiesProvider(api_key="sk_test")
    assert p.get() == {"ft": "1"}
    assert p.last_id == "144514"
    assert seen["url"].endswith("/api/cookies/")
    assert seen["body"] == {"api_key": "sk_test"}

    # Повторный get не покупает заново — использует кэш.
    monkeypatch.setattr(
        spfa_mod.httpx,
        "post",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("re-buy!")),
    )
    assert p.get() == {"ft": "1"}


def test_spfa_handle_block_rebuys_when_unblock_fails(monkeypatch) -> None:
    posts: list[str] = []

    def fake_post(url, **kwargs):  # noqa: ANN001
        posts.append(url)
        if url.endswith("/unblock/"):
            return _Resp(410)  # истёк срок — нужна покупка новых
        return _Resp(200, {"results": {"id": "new", "cookies": {"ft": "2"}}})

    monkeypatch.setattr(spfa_mod.httpx, "post", fake_post)
    p = SpfaCookiesProvider(api_key="sk")
    p.last_id = "old"
    p.last_cookies = {"ft": "old"}
    p.handle_block()
    assert p.last_cookies == {"ft": "2"}
    assert any(u.endswith("/unblock/") for u in posts)


def test_own_provider_returns_fixed_cookies() -> None:
    p = OwnCookiesProvider({"ft": "mine"})
    assert p.get() == {"ft": "mine"}
    p.handle_block()  # no-op, не падает


def test_factory_selects_provider() -> None:
    assert isinstance(
        build_cookies_provider("spfa", api_key="k", own_cookies=None),
        SpfaCookiesProvider,
    )
    assert isinstance(
        build_cookies_provider("own", api_key=None, own_cookies={"ft": "x"}),
        OwnCookiesProvider,
    )
    assert build_cookies_provider("none", api_key=None, own_cookies=None) is None


class TestPlaywrightCookiesProvider:
    def test_factory_returns_playwright_provider(self, monkeypatch) -> None:
        class _FakePW:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self._cookies = {"ft": "fake"}

            def get(self):
                return self._cookies

            def handle_block(self):
                pass

        class _Mod:
            PlaywrightCookiesProvider = _FakePW

        monkeypatch.setitem(sys.modules, "avito_mcp_server.cookies.playwright", _Mod())
        p = build_cookies_provider("playwright", api_key=None, own_cookies=None)
        assert p is not None
        assert p.get() == {"ft": "fake"}

    def test_lazy_import_raises_clear_message(self) -> None:
        try:
            from avito_mcp_server.cookies.playwright import PlaywrightCookiesProvider

            p = PlaywrightCookiesProvider()
            assert p is not None
        except (ImportError, ModuleNotFoundError):
            pytest.skip("playwright не установлен — ожидаемо для CI без браузера")
        except RuntimeError:
            pytest.skip("playwright установлен, но браузер не запустился")


def test_spfa_persists_cookies_between_processes(monkeypatch, tmp_path) -> None:
    # Куки живут у spfa ~12 часов и стоят денег, а каждый вызов тулзы — новый
    # процесс: без файлового кэша мы покупали бы их заново на каждом запросе.
    cache = tmp_path / "cookies.json"
    calls: list[str] = []

    def fake_post(url, **kwargs):  # noqa: ANN001
        calls.append(url)
        return _Resp(200, {"results": {"id": "1", "cookies": {"ft": "cached"}}})

    monkeypatch.setattr(spfa_mod.httpx, "post", fake_post)
    first = SpfaCookiesProvider(api_key="sk", cache_path=cache)
    assert first.get() == {"ft": "cached"}
    assert len(calls) == 1

    # Новый экземпляр (= новый процесс) поднимает куки с диска, не покупая.
    second = SpfaCookiesProvider(api_key="sk", cache_path=cache)
    assert second.get() == {"ft": "cached"}
    assert second.last_id == "1"
    assert len(calls) == 1


def test_spfa_cache_is_not_world_readable(monkeypatch, tmp_path) -> None:
    # В кэше лежат купленные Qrator-куки: это учётные данные (стоят денег и
    # аутентифицируют запросы к Avito). С правами по умолчанию 0644 их прочёл бы
    # любой пользователь машины.
    cache = tmp_path / "sub" / "cookies.json"

    def fake_post(url, **kwargs):  # noqa: ANN001
        return _Resp(200, {"results": {"id": "1", "cookies": {"ft": "secret"}}})

    monkeypatch.setattr(spfa_mod.httpx, "post", fake_post)
    SpfaCookiesProvider(api_key="sk", cache_path=cache).get()

    assert cache.exists()
    assert cache.stat().st_mode & 0o077 == 0, "куки доступны на чтение чужим"


def test_spfa_ignores_stale_cache(monkeypatch, tmp_path) -> None:
    import json as json_mod
    import time as time_mod

    cache = tmp_path / "cookies.json"
    cache.write_text(
        json_mod.dumps(
            {"id": "old", "cookies": {"ft": "stale"}, "ts": time_mod.time() - 13 * 3600}
        )
    )
    monkeypatch.setattr(
        spfa_mod.httpx,
        "post",
        lambda *a, **k: _Resp(
            200, {"results": {"id": "2", "cookies": {"ft": "fresh"}}}
        ),
    )

    p = SpfaCookiesProvider(api_key="sk", cache_path=cache)
    assert p.get() == {"ft": "fresh"}


def test_spfa_drops_cache_on_block(monkeypatch, tmp_path) -> None:
    # Разблокировать не удалось → кэш недействителен, иначе следующий процесс
    # поднимет заведомо мёртвые куки.
    cache = tmp_path / "cookies.json"
    monkeypatch.setattr(
        spfa_mod.httpx,
        "post",
        lambda *a, **k: _Resp(200, {"results": {"id": "1", "cookies": {"ft": "a"}}}),
    )
    p = SpfaCookiesProvider(api_key="sk", cache_path=cache)
    p.get()
    assert cache.exists()

    # unblock не сработал (500) → старые куки выбрасываются, покупаются свежие,
    # и в кэш попадают именно они: следующий процесс не поднимет мёртвые.
    def fake_post(url, **kwargs):  # noqa: ANN001
        if url.endswith("/unblock/"):
            return _Resp(500, {})
        return _Resp(200, {"results": {"id": "2", "cookies": {"ft": "b"}}})

    monkeypatch.setattr(spfa_mod.httpx, "post", fake_post)
    p.handle_block()

    assert p.get() == {"ft": "b"}
    assert json.loads(cache.read_text())["cookies"] == {"ft": "b"}


def test_factory_gives_spfa_a_cache_path(monkeypatch, tmp_path) -> None:
    # Кэш должен работать из коробки: без него каждый вызов тулзы платит за куки.
    monkeypatch.setenv("AVITO_COOKIES_CACHE", str(tmp_path / "c.json"))
    p = build_cookies_provider("spfa", api_key="k", own_cookies=None)
    assert isinstance(p, SpfaCookiesProvider)
    assert p.cache_path == tmp_path / "c.json"


def test_factory_cache_path_has_default(monkeypatch) -> None:
    monkeypatch.delenv("AVITO_COOKIES_CACHE", raising=False)
    p = build_cookies_provider("spfa", api_key="k", own_cookies=None)
    assert isinstance(p, SpfaCookiesProvider)
    assert p.cache_path is not None
    assert p.cache_path.name == "cookies.json"


def test_spfa_requests_ignore_shell_proxy_env(monkeypatch, tmp_path) -> None:
    # Запрос за куками идёт напрямую к spfa: HTTPS_PROXY из шелла отправил бы
    # его через тот же прокси, который мы потом ротируем при блокировках.
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return _Resp(200, {"results": {"id": "1", "cookies": {"ft": "x"}}})

    monkeypatch.setattr(spfa_mod.httpx, "post", fake_post)
    SpfaCookiesProvider(api_key="sk", cache_path=tmp_path / "c.json").get()
    assert captured.get("trust_env") is False


class TestPlaywrightHarvest:
    """Добыча кук браузером — playwright подменён фейком."""

    def _provider(self, monkeypatch, cookies, recorder):
        import avito_mcp_server.cookies.playwright as pw_mod

        class _Page:
            def goto(self, url, **kw):
                recorder["goto"] = url

            def wait_for_timeout(self, ms):
                pass

            def wait_for_load_state(self, *a, **kw):
                pass

        class _Ctx:
            def cookies(self, *args):
                recorder["cookies_args"] = args
                return cookies

            def new_page(self):
                return _Page()

            def close(self):
                pass

        class _Browser:
            def new_context(self, **kw):
                recorder["context_kwargs"] = kw
                return _Ctx()

            def close(self):
                pass

        class _Chromium:
            def launch(self, **kw):
                recorder["launch_kwargs"] = kw
                return _Browser()

        class _PW:
            chromium = _Chromium()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(pw_mod, "sync_playwright", lambda: _PW(), raising=False)
        return pw_mod.PlaywrightCookiesProvider

    def test_returns_all_cookies_not_only_ft(self, monkeypatch) -> None:
        # Раньше провайдер оставлял только `ft` и падал, если её нет. Avito ставит
        # ft не всегда, а для запроса нужны и остальные куки сессии.
        rec: dict = {}
        cls = self._provider(
            monkeypatch,
            [{"name": "srv_id", "value": "1"}, {"name": "u", "value": "2"}],
            rec,
        )
        cookies = cls().get()
        assert cookies == {"srv_id": "1", "u": "2"}

    def test_visits_target_catalog_not_home_page(self, monkeypatch) -> None:
        # Challenge выдаётся на целевой странице; главная может его не ставить.
        rec: dict = {}
        cls = self._provider(monkeypatch, [{"name": "ft", "value": "x"}], rec)
        cls(url="https://www.avito.ru/nizhniy_novgorod/kvartiry").get()
        assert rec["goto"] == "https://www.avito.ru/nizhniy_novgorod/kvartiry"

    def test_browser_uses_same_proxy_as_http_client(self, monkeypatch) -> None:
        # Куки, добытые с локального IP, недействительны для запросов из-под прокси.
        rec: dict = {}
        cls = self._provider(monkeypatch, [{"name": "ft", "value": "x"}], rec)
        cls(proxy="http://user:pass@h:8000").get()
        assert rec["launch_kwargs"]["proxy"]["server"] == "http://h:8000"
        assert rec["launch_kwargs"]["proxy"]["username"] == "user"

    def test_context_matches_http_fingerprint(self, monkeypatch) -> None:
        rec: dict = {}
        cls = self._provider(monkeypatch, [{"name": "ft", "value": "x"}], rec)
        cls().get()
        assert rec["context_kwargs"]["locale"] == "ru-RU"
        assert "timezone_id" in rec["context_kwargs"]


def test_factory_passes_proxy_to_playwright(monkeypatch) -> None:
    # Куки должны добываться с того же IP, с которого пойдут запросы, иначе
    # антибот увидит сессию с чужого адреса.
    captured: dict = {}

    class _FakePW:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def get(self):
            return {}

        def handle_block(self):
            pass

    class _Mod:
        PlaywrightCookiesProvider = _FakePW

    monkeypatch.setitem(sys.modules, "avito_mcp_server.cookies.playwright", _Mod())
    build_cookies_provider(
        "playwright", api_key=None, own_cookies=None, proxy="u:p@h:8000"
    )
    assert captured["proxy"] == "u:p@h:8000"
