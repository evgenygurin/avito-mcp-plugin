"""Тесты HTTP-клиента: rotate-until-clean + follow-редирект (мок сессии)."""

from pathlib import Path

import pytest
from curl_cffi.requests.exceptions import InvalidProxyURL as CffiInvalidProxyURL
from curl_cffi.requests.exceptions import Timeout as CffiTimeout

import avito_mcp_server.http.client as hc
from avito_mcp_server.http.client import HttpClient, fetch_catalog

FIX = Path(__file__).parent / "fixtures"


class _Resp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeSession:
    seq: list = []

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *a) -> bool:  # noqa: ANN002
        return False

    def get(self, url, cookies=None, timeout=None, allow_redirects=True):  # noqa: ANN001
        item = _FakeSession.seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeProxy:
    def __init__(self) -> None:
        self.rotations = 0

    def httpx_proxy(self) -> str:
        return "http://x"

    def rotate(self) -> bool:
        self.rotations += 1
        return True


def test_rotate_until_clean(monkeypatch) -> None:
    _FakeSession.seq = [_Resp(403), _Resp(403), _Resp(200, "<html>ok</html>")]
    monkeypatch.setattr(hc, "_build_session", lambda proxy_url: _FakeSession())
    proxy = _FakeProxy()
    client = HttpClient(proxy=proxy, cookies=None, max_attempts=5, wait_after_rotate=0)
    resp = client.get("https://www.avito.ru/x")
    assert resp.status_code == 200
    assert proxy.rotations == 2  # ротация на каждый из двух 403


def test_get_retries_on_transport_error(monkeypatch) -> None:
    # Живой прогон 2026-07-19: curl_cffi.requests.exceptions.Timeout после
    # ротации на новый IP валил весь процесс — ретрай ловил только коды
    # блокировки (401/403/429), а не транспортные ошибки соединения.
    _FakeSession.seq = [CffiTimeout("timed out"), _Resp(200, "<html>ok</html>")]
    monkeypatch.setattr(hc, "_build_session", lambda proxy_url: _FakeSession())
    proxy = _FakeProxy()
    client = HttpClient(proxy=proxy, cookies=None, max_attempts=3, wait_after_rotate=0)
    resp = client.get("https://www.avito.ru/x")
    assert resp.status_code == 200
    assert proxy.rotations == 1


def test_get_raises_after_max_attempts_on_persistent_transport_error(
    monkeypatch,
) -> None:
    _FakeSession.seq = [CffiTimeout("timed out") for _ in range(5)]
    monkeypatch.setattr(hc, "_build_session", lambda proxy_url: _FakeSession())
    client = HttpClient(
        proxy=_FakeProxy(), cookies=None, max_attempts=3, wait_after_rotate=0
    )
    with pytest.raises(RuntimeError) as exc:
        client.get("https://www.avito.ru/x")
    assert "AVITO_PROXY" in str(exc.value)


def test_get_reraises_configuration_errors_without_retry(monkeypatch) -> None:
    # InvalidProxyURL/InvalidSchema и т.п. — битый конфиг (кривой AVITO_PROXY),
    # не сетевая случайность. Ротация IP её не лечит, поэтому не тратим на
    # неё попытки и не маскируем под общий "нужен чистый RU-прокси".
    _FakeSession.seq = [CffiInvalidProxyURL("bad proxy url")]
    monkeypatch.setattr(hc, "_build_session", lambda proxy_url: _FakeSession())
    proxy = _FakeProxy()
    client = HttpClient(proxy=proxy, cookies=None, max_attempts=5, wait_after_rotate=0)
    with pytest.raises(CffiInvalidProxyURL):
        client.get("https://www.avito.ru/x")
    assert proxy.rotations == 0


def test_get_raises_after_max_attempts(monkeypatch) -> None:
    _FakeSession.seq = [_Resp(403) for _ in range(10)]
    monkeypatch.setattr(hc, "_build_session", lambda proxy_url: _FakeSession())
    client = HttpClient(
        proxy=_FakeProxy(), cookies=None, max_attempts=3, wait_after_rotate=0
    )
    with pytest.raises(RuntimeError) as exc:
        client.get("https://www.avito.ru/x")

    # Исчерпание попыток — самый частый провал; сообщение должно называть выход,
    # иначе агент бесконечно ретраит с того же выжженного IP.
    assert "AVITO_PROXY" in str(exc.value)


def test_fetch_catalog_follows_redirect() -> None:
    stub = (FIX / "redirect_stub.html").read_text(encoding="utf-8")
    catalog = (FIX / "catalog.html").read_text(encoding="utf-8")
    pages = [_Resp(200, stub), _Resp(200, catalog)]

    class _Client:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def get(self, url: str, max_attempts: int | None = None) -> _Resp:
            self.urls.append(url)
            return pages.pop(0)

    client = _Client()
    kind, payload = fetch_catalog(
        client, "https://www.avito.ru/nizhniy_novgorod/kvartiry/prodam"
    )
    assert kind == "ok"
    assert isinstance(payload, dict) and payload.get("items")
    assert len(client.urls) == 2  # исходный + канонический после редиректа


def test_get_honors_max_attempts_override(monkeypatch) -> None:
    # Один и тот же 403 навсегда: без override клиент ушёл бы за пределы
    # заготовленной очереди ответов (IndexError) вместо ожидаемого RuntimeError.
    _FakeSession.seq = [_Resp(403)]
    monkeypatch.setattr(hc, "_build_session", lambda proxy_url: _FakeSession())
    client = HttpClient(
        proxy=_FakeProxy(), cookies=None, max_attempts=18, wait_after_rotate=0
    )
    with pytest.raises(RuntimeError):
        client.get("https://www.avito.ru/x", max_attempts=1)


def test_fetch_catalog_refreshes_redirect_token_after_stale_hop_failure() -> None:
    # Наблюдение из живого прогона: исходный URL пробивается за разумное число
    # ротаций, а КОНКРЕТНЫЙ редирект-URL (одноразовый токен в context=) иногда
    # не пробивается вообще — долбить его дальше бессмысленно, нужен свежий
    # токен с исходного URL.
    stub = (FIX / "redirect_stub.html").read_text(encoding="utf-8")
    catalog = (FIX / "catalog.html").read_text(encoding="utf-8")

    class _Client:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int | None]] = []

        def get(self, url: str, max_attempts: int | None = None) -> _Resp:
            self.calls.append((url, max_attempts))
            if len(self.calls) == 2:
                raise RuntimeError("редирект-цель не пробилась за N попыток")
            if len(self.calls) == 4:
                return _Resp(200, catalog)
            return _Resp(200, stub)

    client = _Client()
    kind, payload = fetch_catalog(
        client, "https://www.avito.ru/nizhniy_novgorod/kvartiry/prodam"
    )
    assert kind == "ok"
    assert isinstance(payload, dict) and payload.get("items")
    assert len(client.calls) == 4
    # исходный URL запрошен дважды (изначально + за свежим токеном после провала)
    assert client.calls[0][0] == client.calls[2][0]
    # редирект-хоп ограничен более низким потолком попыток, чем обычный запрос
    assert client.calls[1][1] is not None
    assert client.calls[1][1] < 18


def test_backoff_grows_and_caps(monkeypatch) -> None:
    # Фиксированные 9 с на каждую блокировку либо слишком долго на первой попытке,
    # либо слишком агрессивно на десятой. Пауза должна расти и упираться в потолок.
    _FakeSession.seq = [_Resp(403) for _ in range(10)]
    waited: list[float] = []
    monkeypatch.setattr(hc, "_build_session", lambda proxy_url: _FakeSession())
    monkeypatch.setattr(hc, "_sleep", waited.append)

    client = HttpClient(
        proxy=_FakeProxy(),
        cookies=None,
        max_attempts=6,
        wait_after_rotate=2.0,
        backoff_cap=10.0,
    )
    with pytest.raises(RuntimeError):
        client.get("https://www.avito.ru/x")

    assert waited == [2.0, 4.0, 8.0, 10.0, 10.0]


def test_backoff_disabled_when_wait_is_zero(monkeypatch) -> None:
    _FakeSession.seq = [_Resp(403) for _ in range(5)]
    waited: list[float] = []
    monkeypatch.setattr(hc, "_build_session", lambda proxy_url: _FakeSession())
    monkeypatch.setattr(hc, "_sleep", waited.append)

    client = HttpClient(
        proxy=_FakeProxy(), cookies=None, max_attempts=3, wait_after_rotate=0
    )
    with pytest.raises(RuntimeError):
        client.get("https://www.avito.ru/x")

    assert waited == [0, 0]


def test_impersonate_profiles_are_current() -> None:
    # curl_cffi резолвит алиас "edge" в edge101 — отпечаток браузера 2022 года,
    # заметный маркер для антибота. Оставляем только актуальные профили.
    assert "edge" not in hc._IMPERSONATE
    assert set(hc._IMPERSONATE) <= {"chrome", "safari"}


def test_session_does_not_override_impersonated_user_agent() -> None:
    # impersonate подставляет UA/Sec-Ch-Ua, согласованные с TLS-отпечатком.
    # Ручной Windows-Chrome UA поверх случайного профиля даёт противоречие:
    # заголовки говорят одно, отпечаток TLS — другое.
    session = hc._build_session(None)
    ua = {k.lower(): v for k, v in dict(session.headers).items()}.get("user-agent")
    assert ua is None or "Windows NT 10.0" not in ua
