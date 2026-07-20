"""Иногда куки мешают: пробовать без них — самое дешёвое лекарство.

Замер 2026-07-20 в момент, когда домашний IP был чист, а куки выгорели:

    без прокси, БЕЗ кук   -> 200 за 0.77 с, каталог получен
    без прокси, С куками  -> 403
    через прокси, с куками -> 403

То есть выгоревшие куки не просто бесполезны — они портят запрос, который без
них проходит. Клиент же всегда прикладывал куки, если провайдер настроен, и
честно перебирал 17 комбинаций IP за 120 с, ни разу не попробовав очевидное.

Попытка без кук не стоит ничего: ни денег, ни секунд, ни платной ротации, —
поэтому в лестнице лечения она идёт первой.
"""

from __future__ import annotations

import avito_mcp_server.http.client as hc
from avito_mcp_server.http.client import HttpClient


class _Resp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _RecordingSession:
    """Запоминает, с какими куками уходил каждый запрос."""

    sent: list = []
    seq: list = []

    def get(self, url, cookies=None, timeout=None, allow_redirects=True):  # noqa: ANN001, ANN201
        _RecordingSession.sent.append(cookies)
        return _RecordingSession.seq.pop(0) if _RecordingSession.seq else _Resp(403)

    def close(self) -> None:
        pass


class _Cookies:
    def get(self) -> dict:
        return {"ft": "выгоревшие"}

    def update(self, resp) -> None:  # noqa: ANN001
        pass

    def handle_block(self) -> bool:
        return True


class _Proxy:
    def __init__(self) -> None:
        self.rotations = 0

    def httpx_proxy(self) -> str:
        return "http://x"

    def rotate(self) -> bool:
        self.rotations += 1
        return True


def _run(monkeypatch, responses, attempts=4):
    _RecordingSession.sent = []
    _RecordingSession.seq = list(responses)
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _RecordingSession()
    )
    proxy = _Proxy()
    client = HttpClient(
        proxy=proxy, cookies=_Cookies(), max_attempts=attempts, wait_after_rotate=0
    )
    try:
        resp = client.get("https://www.avito.ru/x")
    except RuntimeError:
        resp = None
    return resp, proxy, _RecordingSession.sent


def test_retries_without_cookies_after_a_block(monkeypatch) -> None:
    # Первый запрос с куками — 403, второй без кук — 200.
    resp, proxy, sent = _run(monkeypatch, [_Resp(403), _Resp(200, "ok")])

    assert resp is not None and resp.status_code == 200
    assert sent[0], "первый запрос должен идти с куками"
    assert not sent[1], "после блокировки надо попробовать без кук"


def test_cookieless_attempt_costs_no_rotation(monkeypatch) -> None:
    resp, proxy, _ = _run(monkeypatch, [_Resp(403), _Resp(200, "ok")])

    assert proxy.rotations == 0, "бесплатная попытка не должна тратить ротацию"


def test_cookies_come_back_if_cookieless_also_fails(monkeypatch) -> None:
    # Без кук тоже 403 — значит дело не в них, возвращаемся к обычной лестнице.
    _, _, sent = _run(
        monkeypatch, [_Resp(403), _Resp(403), _Resp(403), _Resp(200, "ok")], attempts=4
    )

    assert sent[0] and not sent[1]
    assert sent[2], "дальше лечение идёт как обычно — снова с куками"


def test_cookieless_attempt_does_not_shift_the_ladder(monkeypatch) -> None:
    """Бесплатная попытка без кук не должна вытеснять обновление кук.

    Первая реализация увеличивала на ней счётчик блокировок, сдвигая чётность
    лестницы: нечётные шаги (обновление кук) навсегда съедались попыткой без
    кук, и в живом прогоне ``cookies.refresh`` исчез из сводки совсем —
    осталась только самая дорогая смена адреса.
    """
    refreshed: list[int] = []

    class _TrackingCookies(_Cookies):
        def handle_block(self) -> bool:
            refreshed.append(1)
            return True

    _RecordingSession.sent = []
    _RecordingSession.seq = [_Resp(403) for _ in range(6)]
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _RecordingSession()
    )
    client = HttpClient(
        proxy=_Proxy(),
        cookies=_TrackingCookies(),
        max_attempts=6,
        wait_after_rotate=0,
    )
    try:
        client.get("https://www.avito.ru/x")
    except RuntimeError:
        pass

    assert refreshed, "обновление кук выпало из лестницы совсем"
