"""HTTP-клиент скрапинга: curl_cffi + rotate-until-clean + follow-редирект.

Пул выходных IP смешанный (часть прожжена Qrator). Клиент ротирует IP на каждый
block-код (401/403/429), пока не попадёт на чистый и не получит 200. Затем
``fetch_catalog`` следует SSR-редиректу на канонический URL категории. Схема
воспроизведена и валидирована живьём.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, cast

from curl_cffi import requests as cffi
from curl_cffi.curl import CurlError

from ..cookies.base import CookiesProvider
from ..parser import PageKind, PageResult, classify
from ..proxies.proxy import Proxy
from ..utils import to_absolute_avito_url

# Только алиасы, следующие за свежими версиями браузеров. "edge" исключён:
# curl_cffi резолвит его в edge101 — отпечаток 2022 года, заметный антиботу.
_IMPERSONATE = ("chrome", "safari")
_BLOCK_CODES = (401, 403, 429)

log = logging.getLogger(__name__)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _build_session(proxy_url: str | None, impersonate: str) -> Any:
    session: Any = cffi.Session(impersonate=cast(Any, impersonate))
    # User-Agent НЕ переопределяем: impersonate уже выставил UA, Sec-Ch-Ua и
    # платформу, согласованные с TLS-отпечатком профиля. Ручной Windows-Chrome
    # UA поверх случайного профиля (включая safari) даёт противоречие, по
    # которому антибот отличает автоматизацию от браузера.
    session.headers.update({"accept-language": "ru-RU,ru;q=0.9"})
    if proxy_url:
        session.proxies = {"http": proxy_url, "https": proxy_url}
    return session


class HttpClient:
    def __init__(
        self,
        proxy: Proxy,
        cookies: CookiesProvider | None,
        max_attempts: int = 18,
        wait_after_rotate: float = 9.0,
        timeout: float = 20.0,
        block_codes: tuple[int, ...] = _BLOCK_CODES,
        backoff_cap: float = 60.0,
    ) -> None:
        self.proxy = proxy
        self.cookies = cookies
        self.max_attempts = max_attempts
        self.wait_after_rotate = wait_after_rotate
        self.timeout = timeout
        self.block_codes = block_codes
        self.backoff_cap = backoff_cap
        # Выбирается один раз на клиент, а не на попытку/запрос: fetch_catalog
        # делает несколько client.get() подряд в рамках одной логической
        # цепочки (исходный URL + редирект-хоп), и разные TLS/JA3-отпечатки на
        # соседних запросах — противоречие, которого настоящий браузер не
        # допускает (см. комментарий у _build_session про UA/impersonate).
        self._impersonate = random.choice(_IMPERSONATE)

    def get(self, url: str, max_attempts: int | None = None) -> Any:
        """GET с ротацией IP до чистого. Возвращает 200-ответ или бросает RuntimeError.

        ``max_attempts`` переопределяет лимит попыток для этого вызова — нужно
        для редирект-хопа на одноразовый токен (см. ``fetch_catalog``), где
        долбить один и тот же URL до общего потолка бессмысленно.
        """
        limit = max_attempts if max_attempts is not None else self.max_attempts
        cookies = self.cookies.get() if self.cookies else None
        blocks = 0
        for attempt in range(1, limit + 1):
            log.info("GET %s (попытка %s/%s)", url, attempt, limit)
            try:
                with _build_session(
                    self.proxy.httpx_proxy(), self._impersonate
                ) as session:
                    resp = session.get(
                        url, cookies=cookies, timeout=self.timeout, allow_redirects=True
                    )
            except CurlError as exc:
                if isinstance(exc, ValueError):
                    # Битый конфиг (невалидный AVITO_PROXY/схема URL) — не
                    # сетевая случайность, ротация IP её не лечит. Отдаём
                    # исходную ошибку сразу, а не тратим попытки/маскируем
                    # под общий "нужен чистый RU-прокси".
                    raise
                log.warning("транспортная ошибка (%s) — ротирую IP", exc)
                blocks = self._rotate_and_backoff(attempt, limit, blocks)
                continue
            log.info("ответ %s на попытке %s", resp.status_code, attempt)
            if self.cookies:
                self.cookies.update(resp)
            if resp.status_code in self.block_codes:
                log.warning("блокировка %s — ротирую IP", resp.status_code)
                blocks = self._rotate_and_backoff(attempt, limit, blocks)
                # Каждые 5 блокировок — принудительно обновить куки (могли протухнуть).
                if blocks % 5 == 0 and self.cookies:
                    self.cookies.handle_block()
                cookies = self.cookies.get() if self.cookies else None
                continue
            return resp
        # Без прокси менять нечего: NoProxy.rotate() — заглушка, все попытки идут
        # с одного IP, поэтому подсказка про AVITO_PROXY здесь ключевая.
        via = "прокси не задан" if self.proxy.httpx_proxy() is None else "через прокси"
        raise RuntimeError(
            f"не удалось получить {url} за {limit} попыток "
            f"(блокировки IP, {via}). Нужен чистый RU-прокси: "
            "задайте AVITO_PROXY и AVITO_PROXY_CHANGE_URL"
        )

    def _rotate_and_backoff(self, attempt: int, limit: int, blocks: int) -> int:
        """Сменить IP и выждать нарастающий backoff. Общий путь для кода-блокировки
        и транспортной ошибки — раньше был продублирован в обеих ветках ``get()``.

        Экспоненциальный backoff с потолком: первая блокировка часто случайна,
        а на десятой частые повторы только злят антибот. После последней
        попытки не спим — всё равно сдаёмся.
        """
        self.proxy.rotate()
        if attempt < limit:
            _sleep(min(self.wait_after_rotate * (2**blocks), self.backoff_cap))
        return blocks + 1


# Редирект-URL несёт одноразовый анти-бот токен (``context=``): если он не
# пробивается — дело не в IP, токен уже "использован". Долбить его до общего
# потолка попыток бессмысленно, поэтому здесь лимит ниже, а после исчерпания
# fetch_catalog возвращается на исходный URL за свежим токеном.
_REDIRECT_HOP_ATTEMPTS = 5


def fetch_catalog(
    client: HttpClient,
    url: str,
    max_redirects: int = 3,
    max_token_refreshes: int = 3,
) -> PageResult:
    """Забрать страницу и следовать SSR-редиректу на канонический URL.

    Редирект-цель — одноразовый токен: если конкретный редирект-URL не
    пробивается за ``_REDIRECT_HOP_ATTEMPTS`` попыток, это не проблема IP (тот
    ротируется на каждой попытке), а протухший/спалённый токен — тогда мы
    заново запрашиваем исходный URL за свежим редиректом.

    ``max_redirects`` и ``max_token_refreshes`` — независимые бюджеты:
    первый ограничивает глубину настоящей редирект-цепочки (Avito обычно
    делает один хоп), второй — сколько раз можно попробовать освежить
    протухший токен. Раньше они делили один общий счётчик итераций, из-за
    чего второе освежение токена могло съесть весь бюджет и вернуть
    ``redirect_loop`` вместо ещё одной законной попытки.

    Возвращает результат ``classify``: ``("ok", catalog)`` при успехе, либо
    ``("softblock"|"nojson", None)``; ``("redirect_loop", None)`` при
    исчерпании одного из бюджетов.
    """
    origin_url = url
    current_url = url
    on_redirect_hop = False
    redirects_followed = 0
    refreshes_used = 0
    while True:
        try:
            resp = client.get(
                current_url,
                max_attempts=_REDIRECT_HOP_ATTEMPTS if on_redirect_hop else None,
            )
        except RuntimeError:
            if not on_redirect_hop:
                raise
            refreshes_used += 1
            if refreshes_used > max_token_refreshes:
                return PageKind.REDIRECT_LOOP, None
            log.warning(
                "редирект-цель не пробилась за %s попыток — обновляю токен с "
                "исходного URL",
                _REDIRECT_HOP_ATTEMPTS,
            )
            current_url = origin_url
            on_redirect_hop = False
            # Освежение — это повтор ПЕРВОГО хопа с новым токеном, а не более
            # глубокий шаг в редирект-цепочке: без сброса redirects_followed
            # несколько циклов освежения (в пределах max_token_refreshes)
            # исчерпывали max_redirects и давали ложный redirect_loop без
            # единого реального многошагового редиректа.
            redirects_followed = 0
            continue
        kind, payload = classify(resp.text)
        if kind == PageKind.REDIRECT:
            redirects_followed += 1
            if redirects_followed > max_redirects:
                return PageKind.REDIRECT_LOOP, None
            current_url = to_absolute_avito_url(payload)
            on_redirect_hop = True
            continue
        return kind, payload
