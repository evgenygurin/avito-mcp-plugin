"""Тесты прокси-слоя (mobile/server/none + ротация IP)."""

import avito_mcp_server.proxies.mpsapi as mpsapi_mod
import avito_mcp_server.proxies.proxy as proxy_mod
import avito_mcp_server.proxies.factory as factory_mod
from avito_mcp_server.proxies.factory import build_proxy
from avito_mcp_server.proxies.mpsapi import MpsApiProxy
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


def test_factory_builds_mps_api_proxy_when_configured() -> None:
    p = build_proxy(
        proxy="u:p@h:1",
        change_url="https://chg?k=1",
        mps_api_token="tok",
        mps_proxy_id="520196",
    )
    assert isinstance(p, MpsApiProxy)
    assert p.httpx_proxy() == "http://u:p@h:1"


def test_factory_falls_back_to_mobile_proxy_without_mps_token() -> None:
    # Без токена/proxy_id эскалация невозможна — используем обычную MobileProxy.
    p = build_proxy(proxy="u:p@h:1", change_url="https://chg?k=1")
    assert type(p) is MobileProxy


_GEO_LIST_RESPONSE = {
    "status": "ok",
    "geo_operator_list": {
        "831": {
            "geoid": "831",
            "geo_caption": "Россия, Московская область, Щербинка #2",
            "id_country": "1",
            "count_free": {"megafone": "11"},
        },
        "1099": {
            "geoid": "1099",
            "geo_caption": "Россия, Новосибирск #17",
            "id_country": "1",
            "count_free": {"megafone": "4", "yota": "25"},
        },
        "1123": {
            "geoid": "1123",
            "geo_caption": "Россия, Уфа #12",
            "id_country": "1",
            "count_free": {"megafone": "14", "yota": "5"},
        },
    },
}


class _JsonResp:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


def test_mps_api_proxy_escalate_picks_non_moscow_point(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_get(url, params=None, headers=None, **kw):  # noqa: ANN001
        calls.append(params or {})
        if params["command"] == "get_geo_operator_list":
            return _JsonResp(200, _GEO_LIST_RESPONSE)
        return _JsonResp(200, {"status": "ok"})

    monkeypatch.setattr(mpsapi_mod.httpx, "get", fake_get)
    proxy = MpsApiProxy("u:p@h:1", "https://chg?k=1", "tok", "520196")

    assert proxy.escalate() is True
    change_call = calls[1]
    assert change_call["command"] == "change_equipment"
    # Уфа предпочтён Новосибирску — больше свободных портов megafone (14 > 4),
    # Щербинка (Московская область) исключена как московская точка.
    assert change_call["geoid"] == "1123"
    assert change_call["proxy_id"] == "520196"


def test_mps_api_proxy_escalate_does_not_repeat_tried_geoid(monkeypatch) -> None:
    def fake_get(url, params=None, headers=None, **kw):  # noqa: ANN001
        if params["command"] == "get_geo_operator_list":
            return _JsonResp(200, _GEO_LIST_RESPONSE)
        return _JsonResp(200, {"status": "ok"})

    monkeypatch.setattr(mpsapi_mod.httpx, "get", fake_get)
    proxy = MpsApiProxy("u:p@h:1", "https://chg?k=1", "tok", "520196")

    assert proxy.escalate() is True  # уходит на Уфу (geoid 1123)
    assert proxy.escalate() is True  # Уфа уже испробована — берёт Новосибирск
    assert proxy._tried_geoids == {"1123", "1099"}


def test_mps_api_proxy_escalate_returns_false_without_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        mpsapi_mod.httpx,
        "get",
        lambda url, **kw: _JsonResp(200, {"geo_operator_list": {}}),
    )
    proxy = MpsApiProxy("u:p@h:1", "https://chg?k=1", "tok", "520196")
    assert proxy.escalate() is False


def test_mps_api_proxy_escalate_survives_network_error(monkeypatch) -> None:
    import httpx as real_httpx

    def boom(url, **kw):
        raise real_httpx.HTTPError("нет сети")

    monkeypatch.setattr(mpsapi_mod.httpx, "get", boom)
    proxy = MpsApiProxy("u:p@h:1", "https://chg?k=1", "tok", "520196")
    assert proxy.escalate() is False


def test_cooldown_key_carries_no_credentials() -> None:
    # Пароль прокси не должен уезжать в облачный Postgres: в cooldown пишется
    # host:port, и сверка при следующем запуске идёт по тому же ключу.
    from avito_mcp_server.proxies.proxy import ProxyPool

    class _Store:
        def __init__(self) -> None:
            self.marked: list[str] = []

        def mark_proxy_blocked(self, proxy: str) -> None:
            self.marked.append(proxy)

        def blocked_proxies(self, ttl: float) -> set[str]:
            return set(self.marked)

    store = _Store()
    pool = ProxyPool(["user:secret@1.2.3.4:8000", "user:secret@5.6.7.8:8000"], store)
    pool.rotate()

    assert store.marked == ["1.2.3.4:8000"], "учётные данные не попадают в базу"
    # Второй пул на том же хранилище обязан узнать выжженный адрес и встать на другой.
    assert (
        ProxyPool(
            ["user:secret@1.2.3.4:8000", "user:secret@5.6.7.8:8000"], store
        ).httpx_proxy()
        == "http://user:secret@5.6.7.8:8000"
    )
