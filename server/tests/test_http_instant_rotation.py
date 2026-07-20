"""Мгновенное переключение транспорта не должно стоить паузы.

Смена звена цепочки — это уже другой выходной адрес: ждать, «пока остынет
прежний IP», незачем, а прежний backoff отнимал секунды на ровном месте. Цена
вопроса на живом прогоне: прямое соединение отдаёт каталог за 0.63 с, так что
трёхсекундная пауза перед ним была бы в пять раз дороже самой работы.
"""

from __future__ import annotations

import avito_mcp_server.http.client as hc
from avito_mcp_server.http.client import HttpClient
from avito_mcp_server.proxies.proxy import ChainProxy, NoProxy, ServerProxy


class _Resp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeSession:
    seq: list = []

    def get(self, url, cookies=None, timeout=None, allow_redirects=True):  # noqa: ANN001, ANN201
        return _FakeSession.seq.pop(0)

    def close(self) -> None:
        pass


def test_no_backoff_when_switching_transport(monkeypatch) -> None:
    _FakeSession.seq = [_Resp(403), _Resp(200, "ok")]
    slept: list[float] = []
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    monkeypatch.setattr(hc, "_sleep", slept.append)

    chain = ChainProxy([NoProxy(), ServerProxy("10.0.0.1:8000")])
    client = HttpClient(
        proxy=chain, cookies=None, max_attempts=3, wait_after_rotate=9.0
    )

    assert client.get("https://www.avito.ru/x").status_code == 200
    assert slept == [], f"переключение транспорта стоило паузы: {slept}"


def test_backoff_still_applies_to_real_ip_rotation(monkeypatch) -> None:
    # Ротацию IP через кабинет провайдера паузой сопровождать по-прежнему надо.
    _FakeSession.seq = [_Resp(429), _Resp(429), _Resp(200, "ok")]
    slept: list[float] = []
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    monkeypatch.setattr(hc, "_sleep", slept.append)

    class _Rotating(ServerProxy):
        def rotate(self) -> bool:
            return True

    chain = ChainProxy([NoProxy(), _Rotating("10.0.0.1:8000")])
    client = HttpClient(
        proxy=chain, cookies=None, max_attempts=4, wait_after_rotate=5.0
    )

    client.get("https://www.avito.ru/x")

    # Первая смена (звено) — бесплатно, вторая (IP внутри звена) — с паузой.
    assert len(slept) == 1
    assert slept[0] > 0
