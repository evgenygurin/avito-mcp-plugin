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
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
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
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    proxy = _FakeProxy()
    client = HttpClient(proxy=proxy, cookies=None, max_attempts=3, wait_after_rotate=0)
    resp = client.get("https://www.avito.ru/x")
    assert resp.status_code == 200
    assert proxy.rotations == 1


def test_get_raises_after_max_attempts_on_persistent_transport_error(
    monkeypatch,
) -> None:
    _FakeSession.seq = [CffiTimeout("timed out") for _ in range(5)]
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
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
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    proxy = _FakeProxy()
    client = HttpClient(proxy=proxy, cookies=None, max_attempts=5, wait_after_rotate=0)
    with pytest.raises(CffiInvalidProxyURL):
        client.get("https://www.avito.ru/x")
    assert proxy.rotations == 0


def test_get_raises_after_max_attempts(monkeypatch) -> None:
    _FakeSession.seq = [_Resp(403) for _ in range(10)]
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
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
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
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


def test_fetch_catalog_survives_multiple_token_refresh_cycles() -> None:
    # Живой прогон 2026-07-19: с дефолтным max_redirects=3 общий счётчик
    # итераций делился между "настоящими редиректами" и "обновлениями
    # токена" — после ВТОРОГО обновления бюджет итераций кончался, и
    # fetch_catalog возвращал redirect_loop, хотя логически всё ещё была
    # возможность попробовать освежить токен ещё раз. Глубина реального
    # редиректа и число обновлений токена — независимые бюджеты.
    stub = (FIX / "redirect_stub.html").read_text(encoding="utf-8")
    catalog = (FIX / "catalog.html").read_text(encoding="utf-8")

    class _Client:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int | None]] = []

        def get(self, url: str, max_attempts: int | None = None) -> _Resp:
            self.calls.append((url, max_attempts))
            # Редирект-хоп проваливается ДВАЖДЫ подряд (вызовы 2 и 4),
            # пробивается только на третьей попытке (вызов 6).
            if len(self.calls) in (2, 4):
                raise RuntimeError("редирект-цель не пробилась за N попыток")
            if len(self.calls) == 6:
                return _Resp(200, catalog)
            return _Resp(200, stub)

    client = _Client()
    kind, payload = fetch_catalog(
        client, "https://www.avito.ru/nizhniy_novgorod/kvartiry/prodam"
    )
    assert kind == "ok"
    assert isinstance(payload, dict) and payload.get("items")
    assert len(client.calls) == 6


def test_fetch_catalog_refresh_cycles_dont_exhaust_redirect_depth() -> None:
    # Живой прогон 2026-07-20: redirects_followed инкрементировался на КАЖДОМ
    # успешном получении исходного URL (он всегда классифицируется как
    # "redirect" — так устроен SSR Avito), включая повторные обращения после
    # освежения токена. За 3 полных цикла освежения (в пределах
    # max_token_refreshes=3 по умолчанию) redirects_followed набегал до 4 и
    # превышал max_redirects=3 — ложный redirect_loop без единого реального
    # многошагового редиректа. Освежение токена должно возвращать глубину
    # редирект-цепочки в исходное состояние: это не более глубокий хоп, а
    # повтор того же самого первого хопа с новым токеном.
    stub = (FIX / "redirect_stub.html").read_text(encoding="utf-8")
    catalog = (FIX / "catalog.html").read_text(encoding="utf-8")

    class _Client:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int | None]] = []

        def get(self, url: str, max_attempts: int | None = None) -> _Resp:
            self.calls.append((url, max_attempts))
            # Редирект-хоп проваливается ТРИЖДЫ подряд (вызовы 2, 4, 6) —
            # ровно max_token_refreshes циклов освежения по умолчанию,
            # пробивается только на четвёртой попытке (вызов 8).
            if len(self.calls) in (2, 4, 6):
                raise RuntimeError("редирект-цель не пробилась за N попыток")
            if len(self.calls) == 8:
                return _Resp(200, catalog)
            return _Resp(200, stub)

    client = _Client()
    kind, payload = fetch_catalog(
        client, "https://www.avito.ru/nizhniy_novgorod/kvartiry/prodam"
    )
    assert kind == "ok"
    assert isinstance(payload, dict) and payload.get("items")
    assert len(client.calls) == 8


def test_backoff_grows_and_caps(monkeypatch) -> None:
    # Фиксированные 9 с на каждую блокировку либо слишком долго на первой попытке,
    # либо слишком агрессивно на десятой. Пауза должна расти и упираться в потолок.
    _FakeSession.seq = [_Resp(403) for _ in range(10)]
    waited: list[float] = []
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
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
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
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
    session = hc._build_session(None, "chrome")
    ua = {k.lower(): v for k, v in dict(session.headers).items()}.get("user-agent")
    assert ua is None or "Windows NT 10.0" not in ua


def test_impersonate_profile_is_fixed_per_client(monkeypatch) -> None:
    # A4 (Context7-аудит): профиль (TLS/JA3/UA) выбирался заново на КАЖДУЮ
    # попытку внутри одного client.get(), а fetch_catalog делает несколько
    # client.get() подряд (исходный URL + редирект-хоп) — с вероятностью 50%
    # они уходили с разными семействами отпечатков в рамках одной логической
    # цепочки, чего реальный браузер не делает. Профиль должен фиксироваться
    # один раз на инстанс HttpClient.
    _FakeSession.seq = [_Resp(403), _Resp(200, "<html>ok</html>")]
    seen_profiles: list[str] = []

    def _fake_build_session(proxy_url, impersonate):
        seen_profiles.append(impersonate)
        return _FakeSession()

    monkeypatch.setattr(hc, "_build_session", _fake_build_session)
    client = HttpClient(
        proxy=_FakeProxy(), cookies=None, max_attempts=5, wait_after_rotate=0
    )
    client.get("https://www.avito.ru/x")

    assert len(seen_profiles) == 2  # одна ротация — два вызова _build_session
    assert seen_profiles[0] == seen_profiles[1], (
        "профиль должен быть одним и тем же на протяжении всех попыток клиента"
    )


def test_fetch_catalog_gives_up_with_redirect_loop(monkeypatch) -> None:
    # Страница вечно редиректит: бюджет глубины обязан закончиться понятным
    # статусом, а не бесконечным хождением по кругу.
    from avito_mcp_server.parser import PageKind

    hops: list[str] = []

    class _Client:
        def get(self, url: str, max_attempts: int | None = None):
            hops.append(url)
            return type("R", (), {"text": ""})()

    monkeypatch.setattr(hc, "classify", lambda text: (PageKind.REDIRECT, "/next-hop"))
    kind, payload = fetch_catalog(_Client(), "https://www.avito.ru/x", max_redirects=2)

    assert (kind, payload) == (PageKind.REDIRECT_LOOP, None)
    assert len(hops) == 3, "исходный запрос + ровно max_redirects хопов"


class _DeadEndProxy:
    """Прокси, которому больше нечего ротировать (пул исчерпан / NoProxy)."""

    def __init__(self) -> None:
        self.rotations = 0

    def httpx_proxy(self) -> str:
        return "http://x"

    def rotate(self) -> bool:
        self.rotations += 1
        return False


def test_get_gives_up_when_rotation_is_impossible(monkeypatch) -> None:
    # rotate() == False означает «сменить IP нечем»: повторять с того же
    # адреса бессмысленно, а 18 попыток с backoff — это ~15 минут ожидания
    # заведомо того же 403.
    _FakeSession.seq = [_Resp(403)] * 18
    waited: list[float] = []
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    monkeypatch.setattr(hc, "_sleep", waited.append)
    proxy = _DeadEndProxy()
    client = HttpClient(
        proxy=proxy, cookies=None, max_attempts=18, wait_after_rotate=9.0
    )

    with pytest.raises(RuntimeError):
        client.get("https://www.avito.ru/x")

    assert proxy.rotations == 1, "одна попытка ротации — и сразу отказ"
    assert waited == [], "спать после безнадёжной ротации нельзя"


def test_fetch_page_follows_ssr_redirect(monkeypatch) -> None:
    # Страница объявления тоже может прийти SSR-редиректом на канонический
    # URL: без хопа парсер получит страницу-редирект и вернёт None.
    from avito_mcp_server.parser import PageKind

    hops: list[str] = []
    pages = iter([(PageKind.REDIRECT, "/canonical"), (PageKind.NOJSON, None)])

    class _Client:
        def get(self, url: str, max_attempts: int | None = None):
            hops.append(url)
            return type("R", (), {"text": url})()

    monkeypatch.setattr(hc, "classify", lambda text: next(pages))
    resp = hc.fetch_page(_Client(), "https://www.avito.ru/items/1")

    assert hops == ["https://www.avito.ru/items/1", "https://www.avito.ru/canonical"]
    assert resp.text == "https://www.avito.ru/canonical"


def test_get_raises_contract_error_when_attempts_disabled(monkeypatch) -> None:
    # AVITO_MAX_ROTATE_ATTEMPTS=0 — законный способ «не ротировать»: наружу
    # должен уйти контрактный RuntimeError, а не UnboundLocalError.
    _FakeSession.seq = []
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    client = HttpClient(proxy=_FakeProxy(), cookies=None, max_attempts=0)

    with pytest.raises(RuntimeError, match="за 0 из 0 попыток"):
        client.get("https://www.avito.ru/x")


class _EscalatingDeadEndProxy:
    """Ротация невозможна, но эскалация (смена региона/оператора) — да."""

    def __init__(self) -> None:
        self.rotations = 0
        self.escalations = 0

    def httpx_proxy(self) -> str:
        return "http://x"

    def rotate(self) -> bool:
        self.rotations += 1
        return False

    def escalate(self) -> bool:
        self.escalations += 1
        return True


def test_get_escalates_proxy_after_exhausting_rotation(monkeypatch) -> None:
    # Живой прогон 2026-07-20: вся подсеть мобильного прокси прожжена, обычная
    # ротация IP не спасает. После исчерпания круга попыток клиент должен
    # попробовать эскалировать прокси (смена региона/оператора) и повторить.
    _FakeSession.seq = [_Resp(403), _Resp(200, "<html>ok</html>")]
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    proxy = _EscalatingDeadEndProxy()
    client = HttpClient(proxy=proxy, cookies=None, max_attempts=1, wait_after_rotate=0)

    resp = client.get("https://www.avito.ru/x")

    assert resp.status_code == 200
    assert proxy.escalations == 1


def test_get_raises_when_escalation_also_fails(monkeypatch) -> None:
    _FakeSession.seq = [_Resp(403)]
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    client = HttpClient(
        proxy=_DeadEndProxy(), cookies=None, max_attempts=1, wait_after_rotate=0
    )
    with pytest.raises(RuntimeError):
        client.get("https://www.avito.ru/x")


def test_get_escalates_at_most_once_per_call(monkeypatch) -> None:
    # Если и после эскалации блок держится — сдаёмся, а не эскалируем бесконечно.
    _FakeSession.seq = [_Resp(403), _Resp(403)]
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    proxy = _EscalatingDeadEndProxy()
    client = HttpClient(proxy=proxy, cookies=None, max_attempts=1, wait_after_rotate=0)

    with pytest.raises(RuntimeError):
        client.get("https://www.avito.ru/x")

    assert proxy.escalations == 1


def test_transport_errors_retry_even_without_rotation(monkeypatch) -> None:
    # Таймаут — не блокировка: он лечится повтором, а не сменой IP. Без
    # прокси (rotate() всегда False) обрывать на первой ошибке нельзя.
    _FakeSession.seq = [CffiTimeout("timeout"), _Resp(200, "<html>ok</html>")]
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    client = HttpClient(
        proxy=_DeadEndProxy(), cookies=None, max_attempts=3, wait_after_rotate=0
    )

    assert client.get("https://www.avito.ru/x").status_code == 200
