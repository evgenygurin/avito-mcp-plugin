"""Попытка не должна тратиться на «лечение», которого не было.

Лестница лечения чередует обновление кук со сменой адреса. Но обновление
может не состояться: провайдер ``own`` не умеет обновлять куки в принципе, а
``spfa`` троттлит покупки, чтобы не словить свой 429. Если после такого
несостоявшегося лечения просто повторить запрос, следующая попытка уйдёт с тем
же IP и теми же куками — заведомо в тот же 403, но за счёт бюджета.

Поэтому провайдер сообщает, изменилось ли что-нибудь, и при «нет» клиент сразу
переходит к смене адреса, а не жжёт попытку впустую.
"""

from __future__ import annotations

import avito_mcp_server.http.client as hc
from avito_mcp_server.http.client import HttpClient


class _Resp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeSession:
    seq: list = []

    def get(self, url, cookies=None, timeout=None, allow_redirects=True):  # noqa: ANN001, ANN201
        return _FakeSession.seq.pop(0) if _FakeSession.seq else _Resp(403)

    def close(self) -> None:
        pass


class _CountingProxy:
    def __init__(self) -> None:
        self.rotations = 0

    def httpx_proxy(self) -> str:
        return "http://x"

    def rotate(self) -> bool:
        self.rotations += 1
        return True


class _UselessCookies:
    """Провайдер, который лечить не умеет (как ``own`` или spfa под троттлингом)."""

    def __init__(self) -> None:
        self.attempts = 0

    def get(self) -> dict:
        return {}

    def update(self, resp) -> None:  # noqa: ANN001
        pass

    def handle_block(self) -> bool:
        self.attempts += 1
        return False


def test_failed_cookie_refresh_falls_through_to_changing_address(
    monkeypatch,
) -> None:
    _FakeSession.seq = [_Resp(403) for _ in range(4)]
    monkeypatch.setattr(
        hc, "_build_session", lambda proxy_url, impersonate: _FakeSession()
    )
    proxy, cookies = _CountingProxy(), _UselessCookies()
    client = HttpClient(
        proxy=proxy, cookies=cookies, max_attempts=4, wait_after_rotate=0
    )

    try:
        client.get("https://www.avito.ru/x")
    except RuntimeError:
        pass

    # Куки лечить не смогли ни разу — значит каждую блокировку обязан был
    # разруливать адрес, иначе попытки уходят в пустоту.
    assert cookies.attempts >= 1
    assert proxy.rotations >= 3, (
        f"{proxy.rotations} смен адреса на 4 блокировки — попытки потрачены впустую"
    )
