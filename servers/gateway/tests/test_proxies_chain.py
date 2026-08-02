"""Цепочка транспортов: сначала прямое соединение, прокси — фоллбэк.

Замер 2026-07-20 на живом Avito (куки spfa из кэша, возраст 1.5 ч):

    без прокси, без кук      -> 403
    без прокси, С куками     -> 200 за 0.63с, каталог получен
    через прокси, с куками   -> 403
    через прокси, safari     -> 403

Купленная мобильная подсеть забанена Qrator целиком — ротация IP внутри неё
меняет адрес, но не репутацию, поэтому 403 держится на любом. При этом прямое
соединение отдаёт каталог за 0.6 с. Прежний клиент весь трафик гнал в прокси и
честно выбирал бюджет 120 с на попытки, у которых не было шанса.

Отсюда цепочка: звенья пробуются по порядку, переключение между ними —
мгновенное и без backoff (это уже другой выходной адрес, «остывать» нечему), и
только когда звенья кончились, идёт дорогая ротация IP внутри последнего.
"""

from __future__ import annotations

from avito_mcp_server.proxies.proxy import (
    ChainProxy,
    MobileProxy,
    NoProxy,
    ServerProxy,
)


class _Spy(ServerProxy):
    """Прокси со счётчиками — видно, кого и сколько раз дёрнули."""

    def __init__(self, url: str, can_rotate: bool = True) -> None:
        super().__init__(url)
        self.rotations = 0
        self.escalations = 0
        self.can_rotate = can_rotate

    def rotate(self) -> bool:
        self.rotations += 1
        return self.can_rotate

    def escalate(self) -> bool:
        self.escalations += 1
        return True


def test_starts_with_the_first_link() -> None:
    chain = ChainProxy([NoProxy(), _Spy("10.0.0.1:8000")])

    # Прямое соединение — первым: оно и быстрее, и бесплатно.
    assert chain.httpx_proxy() is None


def test_rotate_switches_to_the_next_link() -> None:
    chain = ChainProxy([NoProxy(), _Spy("10.0.0.1:8000")])

    assert chain.rotate() is True
    assert chain.httpx_proxy() == "http://10.0.0.1:8000"


def test_switching_links_is_free_and_needs_no_backoff() -> None:
    # Переключение на другое звено уже даёт другой выходной адрес — пауза
    # «чтобы прежний IP остыл» здесь бессмысленна и стоила бы секунд на ровном месте.
    chain = ChainProxy([NoProxy(), _Spy("10.0.0.1:8000")])

    chain.rotate()

    assert chain.rotation_was_instant is True


def test_ip_rotation_inside_the_last_link_is_not_instant() -> None:
    spy = _Spy("10.0.0.1:8000")
    chain = ChainProxy([NoProxy(), spy])
    chain.rotate()  # перешли на прокси

    assert chain.rotate() is True  # звенья кончились — меняем IP внутри прокси

    assert spy.rotations == 1
    assert chain.rotation_was_instant is False


def test_does_not_rotate_ip_of_earlier_links() -> None:
    # Дорогая ротация касается только последнего звена: дёргать смену IP у
    # прямого соединения нечего, а у промежуточных — рано.
    first = _Spy("10.0.0.1:8000")
    last = _Spy("10.0.0.2:8000")
    chain = ChainProxy([first, last])

    chain.rotate()  # first -> last (бесплатно)
    chain.rotate()  # ротация IP внутри last

    assert first.rotations == 0
    assert last.rotations == 1


def test_reports_exhaustion_when_last_link_cannot_rotate() -> None:
    chain = ChainProxy([NoProxy(), _Spy("10.0.0.1:8000", can_rotate=False)])
    chain.rotate()

    assert chain.rotate() is False


def test_escalate_delegates_to_the_last_link() -> None:
    spy = _Spy("10.0.0.1:8000")
    chain = ChainProxy([NoProxy(), spy])

    assert chain.escalate() is True
    assert spy.escalations == 1


def test_single_link_chain_behaves_like_that_link() -> None:
    spy = _Spy("10.0.0.1:8000")
    chain = ChainProxy([spy])

    assert chain.httpx_proxy() == "http://10.0.0.1:8000"
    chain.rotate()
    assert spy.rotations == 1


def test_rejects_an_empty_chain() -> None:
    import pytest

    with pytest.raises(ValueError, match="пуст"):
        ChainProxy([])


def test_mobile_proxy_can_be_the_last_link() -> None:
    # Типовая боевая связка: прямое соединение + мобильный прокси с ротацией.
    chain = ChainProxy(
        [NoProxy(), MobileProxy("user:pass@10.0.0.1:8000", "https://cabinet/change")]
    )

    assert chain.httpx_proxy() is None
    chain.rotate()
    assert chain.httpx_proxy() == "http://user:pass@10.0.0.1:8000"
