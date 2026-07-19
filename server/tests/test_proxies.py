"""Тесты прокси-слоя (mobile/server/none + ротация IP)."""

import avito_mcp_server.proxies.proxy as proxy_mod
import avito_mcp_server.proxies.factory as factory_mod
from avito_mcp_server.proxies.factory import build_proxy
from avito_mcp_server.proxies.proxy import MobileProxy, NoProxy, ProxyPool, ServerProxy


def test_factory_mobile_when_change_url() -> None:
    p = build_proxy(proxy="u:p@h:1", change_url="https://chg?k=1")
    assert isinstance(p, MobileProxy)
    assert p.httpx_proxy() == "http://u:p@h:1"


def test_factory_server_when_no_change_url() -> None:
    assert isinstance(build_proxy(proxy="u:p@h:1", change_url=""), ServerProxy)


def test_factory_none_when_empty() -> None:
    p = build_proxy(proxy="", change_url="")
    assert isinstance(p, NoProxy)
    assert p.httpx_proxy() is None


def test_mobile_rotate_ok(monkeypatch) -> None:
    called: dict = {}

    class _R:
        status_code = 200

        def json(self) -> dict:
            return {"new_ip": "1.2.3.4"}

    def fake_get(url, **kwargs):  # noqa: ANN001
        called["url"] = str(url)
        return _R()

    monkeypatch.setattr(proxy_mod.httpx, "get", fake_get)
    assert MobileProxy("u:p@h:1", "https://chg?k=1").rotate() is True
    assert "format=json" in called["url"]


def test_server_rotate_is_noop() -> None:
    assert ServerProxy("u:p@h:1").rotate() is False


def test_mobile_rotate_handles_invalid_change_url() -> None:
    # httpx.InvalidURL наследует Exception, а НЕ HTTPError (проверено в httpx
    # 0.28.1) — опечатка/битый плейсхолдер в AVITO_PROXY_CHANGE_URL не должны
    # ронять rotate() сырым исключением: контракт метода — вернуть False.
    assert MobileProxy("u:p@h:1", "http://host:notaport/").rotate() is False


def test_pool_from_comma_separated_list() -> None:
    # Один выжженный IP не должен останавливать работу: пул перебирает адреса.
    pool = build_proxy(proxy="u:p@h1:1, u:p@h2:2", change_url="")
    assert isinstance(pool, ProxyPool)
    assert pool.httpx_proxy() == "http://u:p@h1:1"
    assert pool.rotate() is True
    assert pool.httpx_proxy() == "http://u:p@h2:2"


def test_pool_wraps_around_and_reports_exhaustion() -> None:
    pool = ProxyPool(["a:1", "b:2"])
    pool.rotate()
    # Круг замкнулся — прокси кончились, вызывающему нужен сигнал.
    assert pool.rotate() is False
    assert pool.httpx_proxy() == "http://a:1"


def test_pool_rotates_ip_when_change_url_given(monkeypatch) -> None:
    # Один мобильный прокси со сменой IP: ротация — это смена IP, не адреса.
    calls: list[str] = []

    class _R:
        status_code = 200

    monkeypatch.setattr(
        proxy_mod.httpx, "get", lambda url, **kw: (calls.append(str(url)), _R())[1]
    )
    pool = build_proxy(proxy="u:p@h:1", change_url="https://chg?k=1")
    assert pool.rotate() is True
    assert calls and "format=json" in calls[0]


def test_single_proxy_without_change_url_is_server_proxy() -> None:
    assert isinstance(build_proxy(proxy="u:p@h:1", change_url=""), ServerProxy)


class _FakeCooldown:
    def __init__(self, blocked: set[str] | None = None) -> None:
        self.blocked = blocked or set()
        self.marked: list[str] = []

    def blocked_proxies(self, ttl: float) -> set[str]:
        return self.blocked

    def mark_proxy_blocked(self, proxy: str) -> None:
        self.marked.append(proxy)
        self.blocked.add(proxy)


def test_pool_skips_proxies_in_cooldown() -> None:
    # h1 дал 403 в прошлом запуске — начинаем сразу с h2, не тратя на него попытку.
    store = _FakeCooldown({"h1:1"})
    pool = ProxyPool(["h1:1", "h2:2"], cooldown_store=store)
    assert pool.httpx_proxy() == "http://h2:2"


def test_pool_marks_blocked_on_rotate() -> None:
    store = _FakeCooldown()
    pool = ProxyPool(["h1:1", "h2:2"], cooldown_store=store)
    pool.rotate()
    # rotate() вызывается именно после блокировки — адрес попадает в cooldown.
    assert store.marked == ["h1:1"]
    assert pool.httpx_proxy() == "http://h2:2"


def test_pool_uses_all_when_everything_cooled_down() -> None:
    # Все адреса в cooldown — работать всё равно надо, иначе плагин мёртв.
    store = _FakeCooldown({"h1:1", "h2:2"})
    pool = ProxyPool(["h1:1", "h2:2"], cooldown_store=store)
    assert pool.httpx_proxy() in ("http://h1:1", "http://h2:2")


class TestProxyListUrl:
    def test_parses_plain_text_lines(self, monkeypatch) -> None:
        # Кабинеты прокси часто отдают список портов простым текстом.
        class _R:
            status_code = 200
            text = "u:p@h1:1\nu:p@h2:2\n\n"

            def json(self):
                raise ValueError("не json")

        monkeypatch.setattr(factory_mod.httpx, "get", lambda url, **kw: _R())
        assert factory_mod.fetch_proxy_list("https://api.example/list") == [
            "u:p@h1:1",
            "u:p@h2:2",
        ]

    def test_parses_json_array(self, monkeypatch) -> None:
        class _R:
            status_code = 200
            text = '["u:p@h1:1", "u:p@h2:2"]'

            def json(self):
                return ["u:p@h1:1", "u:p@h2:2"]

        monkeypatch.setattr(factory_mod.httpx, "get", lambda url, **kw: _R())
        assert factory_mod.fetch_proxy_list("https://api.example/list") == [
            "u:p@h1:1",
            "u:p@h2:2",
        ]

    def test_network_failure_returns_empty(self, monkeypatch) -> None:
        # Недоступный кабинет не должен ронять парсинг — падаем на AVITO_PROXY.
        def boom(url, **kwargs):
            raise factory_mod.httpx.HTTPError("нет сети")

        monkeypatch.setattr(factory_mod.httpx, "get", boom)
        assert factory_mod.fetch_proxy_list("https://api.example/list") == []

    def test_invalid_url_returns_empty(self) -> None:
        # httpx.InvalidURL наследует Exception, а НЕ HTTPError (проверено в
        # httpx 0.28.1) — кривой AVITO_PROXY_LIST_URL (опечатка, невалидный
        # порт) должен падать на тот же путь, что и обычный сетевой сбой,
        # а не пробрасывать сырое исключение через весь build_http_client().
        assert factory_mod.fetch_proxy_list("http://user:pass@host:notaport/path") == []


def test_rotate_ignores_shell_proxy_env(monkeypatch) -> None:
    # change-IP URL — служебный запрос к кабинету провайдера. С trust_env=True
    # он ушёл бы через HTTPS_PROXY из шелла, то есть через сам ротируемый прокси.
    captured: dict = {}

    class _R:
        status_code = 200

    def fake_get(url, **kwargs):
        captured.update(kwargs)
        return _R()

    monkeypatch.setattr(proxy_mod.httpx, "get", fake_get)
    MobileProxy("u:p@h:1", "https://chg?k=1").rotate()
    assert captured.get("trust_env") is False


def test_rotate_follows_redirects(monkeypatch) -> None:
    # Кабинеты часто отвечают 302 на change-IP; без follow_redirects ротация
    # считалась бы неуспешной, хотя IP сменился.
    captured: dict = {}

    class _R:
        status_code = 200

    monkeypatch.setattr(
        proxy_mod.httpx, "get", lambda url, **kw: (captured.update(kw), _R())[1]
    )
    MobileProxy("u:p@h:1", "https://chg?k=1").rotate()
    assert captured.get("follow_redirects") is True


def test_proxy_list_follows_redirects(monkeypatch) -> None:
    # AVITO_PROXY_LIST_URL — пользовательский URL кабинета: 301/302
    # (http->https, trailing slash, CDN) обычны. httpx (в отличие от requests)
    # по умолчанию редиректы не проходит — без follow_redirects список тихо
    # терялся бы, и код фоллбэкал на одиночный AVITO_PROXY.
    captured: dict = {}

    class _R:
        status_code = 200
        text = "u:p@h1:1"

        def json(self):
            raise ValueError("не json")

    monkeypatch.setattr(
        factory_mod.httpx, "get", lambda url, **kw: (captured.update(kw), _R())[1]
    )
    factory_mod.fetch_proxy_list("https://api.example/list")
    assert captured.get("follow_redirects") is True


def test_proxy_list_ignores_shell_proxy_env(monkeypatch) -> None:
    captured: dict = {}

    class _R:
        status_code = 200
        text = "u:p@h1:1"

        def json(self):
            raise ValueError("не json")

    monkeypatch.setattr(
        factory_mod.httpx, "get", lambda url, **kw: (captured.update(kw), _R())[1]
    )
    factory_mod.fetch_proxy_list("https://api.example/list")
    assert captured.get("trust_env") is False
