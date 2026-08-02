"""Тесты переиспользования curl_cffi-сессии между запросами.

Раньше сессия собиралась заново на КАЖДУЮ попытку: обход десяти страниц (плюс
редирект-хоп на каждой) — это два десятка полных TLS-рукопожатий, а через
мобильный прокси к ним добавляется CONNECT. Замер на прямом соединении дал
~134 мс лишних на запрос; через прокси цена выше.

Обратная сторона: держать keep-alive соединение поверх смены выходного IP
нельзя — установленный TCP-канал остаётся на старом (прожжённом) адресе, и
ротация превращается в фикцию. Поэтому после ротации сессия обязана умирать.
"""

from __future__ import annotations

import pytest

import avito_mcp_server.http.client as hc
from avito_mcp_server.http.client import HttpClient


class _Resp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False
        self.requests = 0

    def get(self, url, cookies=None, timeout=None, allow_redirects=True):  # noqa: ANN001, ANN201
        self.requests += 1
        item = _FakeSession.seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self) -> None:
        self.closed = True

    seq: list = []


class _FakeProxy:
    def __init__(self, url: str = "http://x") -> None:
        self.url = url
        self.rotations = 0

    def httpx_proxy(self) -> str:
        return self.url

    def rotate(self) -> bool:
        self.rotations += 1
        return True


@pytest.fixture
def built(monkeypatch):
    """Собранные сессии по порядку — в них видно, сколько раз строили заново."""
    sessions: list[_FakeSession] = []

    def _build(proxy_url, impersonate):  # noqa: ANN001, ANN202
        session = _FakeSession()
        sessions.append(session)
        return session

    monkeypatch.setattr(hc, "_build_session", _build)
    return sessions


def test_session_is_reused_across_requests(built) -> None:
    _FakeSession.seq = [_Resp(200, "a"), _Resp(200, "b"), _Resp(200, "c")]
    client = HttpClient(proxy=_FakeProxy(), cookies=None, max_attempts=3)

    for _ in range(3):
        client.get("https://www.avito.ru/x")

    assert len(built) == 1
    assert built[0].requests == 3


def test_session_is_rebuilt_after_ip_rotation(built) -> None:
    _FakeSession.seq = [_Resp(403), _Resp(200, "ok")]
    proxy = _FakeProxy()
    client = HttpClient(proxy=proxy, cookies=None, max_attempts=3, wait_after_rotate=0)

    client.get("https://www.avito.ru/x")

    assert proxy.rotations == 1
    assert len(built) == 2, "keep-alive поверх смены IP свёл бы ротацию на нет"
    assert built[0].closed is True


def test_session_is_rebuilt_after_transport_error(built) -> None:
    from curl_cffi.requests.exceptions import Timeout as CffiTimeout

    _FakeSession.seq = [CffiTimeout("timed out"), _Resp(200, "ok")]
    client = HttpClient(
        proxy=_FakeProxy(), cookies=None, max_attempts=3, wait_after_rotate=0
    )

    client.get("https://www.avito.ru/x")

    # Оборванное соединение переиспользовать нельзя — только строить заново.
    assert len(built) == 2


def test_close_releases_the_session(built) -> None:
    _FakeSession.seq = [_Resp(200, "ok")]
    client = HttpClient(proxy=_FakeProxy(), cookies=None, max_attempts=1)
    client.get("https://www.avito.ru/x")

    client.close()

    assert built[0].closed is True
    # Повторное закрытие — не ошибка: тулза зовёт close() в finally.
    client.close()


def test_client_works_as_context_manager(built) -> None:
    _FakeSession.seq = [_Resp(200, "ok")]
    with HttpClient(proxy=_FakeProxy(), cookies=None, max_attempts=1) as client:
        client.get("https://www.avito.ru/x")

    assert built[0].closed is True


def test_session_is_rebuilt_when_proxy_address_changes(built) -> None:
    # ProxyPool.rotate() меняет сам адрес прокси, а не только выходной IP.
    _FakeSession.seq = [_Resp(200, "a"), _Resp(200, "b")]
    proxy = _FakeProxy()
    client = HttpClient(proxy=proxy, cookies=None, max_attempts=1)

    client.get("https://www.avito.ru/x")
    proxy.url = "http://y"
    client.get("https://www.avito.ru/x")

    assert len(built) == 2
