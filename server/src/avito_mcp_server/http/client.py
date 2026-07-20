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
from contextlib import suppress
from typing import Any, cast

from curl_cffi import requests as cffi
from curl_cffi.curl import CurlError

from ..cookies.base import CookiesProvider
from ..parser import PageKind, PageResult, classify, explain_status
from ..proxies.proxy import Proxy
from ..timing import timed
from ..utils import mask_proxy, to_absolute_avito_url

# Только алиасы, следующие за свежими версиями браузеров. "edge" исключён:
# curl_cffi резолвит его в edge101 — отпечаток 2022 года, заметный антиботу.
_IMPERSONATE = ("chrome", "safari")
_BLOCK_CODES = (401, 403, 429)
#: Коды, которые действительно лечатся ожиданием. 429 — «слишком часто», пауза
#: тут по существу. А 403/401 означают «этот выходной IP или эти куки в бане у
#: Qrator»: репутация адреса не восстанавливается за десятки секунд, лечится
#: только смена комбинации (транспорт/куки/IP). Живой прогон 2026-07-20 показал
#: цену смешения — ``backoff.sleep=90.6s`` из 120 с бюджета при 3.7 с полезной
#: работы и 11 ответах 403 против 2 ответов 429.
_RATE_LIMIT_CODES = (429,)

#: Через сколько блокировок принудительно обновлять куки. У 403 две независимые
#: причины — выгоревшие куки и забаненный выходной IP, и замеры 2026-07-20
#: показали, что они меняются местами в течение получаса. Лечение кук стоит
#: 0.6 с против 3.6–4.3 с на ротацию IP, поэтому пробовать его надо рано; но не
#: на каждой блокировке — сначала бесплатная смена транспорта (см. ChainProxy),
#: а покупка кук стоит денег. Раньше здесь стояло 5 — куки успевали обновиться
#: только после того, как бюджет времени был практически выбран.
_COOKIE_REFRESH_EVERY = 2

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
        max_attempts: int = 5,
        wait_after_rotate: float = 3.0,
        timeout: float = 20.0,
        block_codes: tuple[int, ...] = _BLOCK_CODES,
        backoff_cap: float = 15.0,
        budget: float | None = None,
    ) -> None:
        self.proxy = proxy
        self.cookies = cookies
        self.max_attempts = max_attempts
        self.wait_after_rotate = wait_after_rotate
        self.timeout = timeout
        self.block_codes = block_codes
        self.backoff_cap = backoff_cap
        # Жёсткий потолок wall-clock на клиента: лимиты попыток перемножаются
        # (max_attempts × max_token_refreshes × попытки редирект-хопа × круг
        # эскалации), и верхней границы по времени у этого произведения нет.
        # Таймаут тулзы её не заменяет: `asyncio.to_thread` не отменяется, и
        # поток продолжает жечь платные ротации уже после отказа клиенту.
        self.budget = budget
        self._started = time.monotonic()
        # Выбирается один раз на клиент, а не на попытку/запрос: fetch_catalog
        # делает несколько client.get() подряд в рамках одной логической
        # цепочки (исходный URL + редирект-хоп), и разные TLS/JA3-отпечатки на
        # соседних запросах — противоречие, которого настоящий браузер не
        # допускает (см. комментарий у _build_session про UA/impersonate).
        self._impersonate = random.choice(_IMPERSONATE)
        self._session: Any | None = None
        self._session_proxy: str | None = None

    def _remaining(self) -> float:
        """Сколько секунд бюджета осталось (``inf``, если бюджета нет)."""
        if self.budget is None:
            return float("inf")
        return self.budget - (time.monotonic() - self._started)

    def _out_of_budget(self) -> bool:
        return self._remaining() <= 0

    def _get_session(self) -> Any:
        """Сессия под текущий выходной адрес; переиспользуется между запросами.

        Новая сессия — это полное TLS-рукопожатие (а через прокси ещё и
        CONNECT). Обход каталога делает по два запроса на страницу, и раньше
        каждый начинался с нуля: замер дал ~134 мс лишних на запрос даже на
        прямом соединении.

        Сессия привязана к адресу прокси и умирает при его смене — см.
        ``_drop_session``.
        """
        proxy_url = self.proxy.httpx_proxy()
        if self._session is None or self._session_proxy != proxy_url:
            self._drop_session()
            self._session = _build_session(proxy_url, self._impersonate)
            self._session_proxy = proxy_url
        return self._session

    def _drop_session(self) -> None:
        """Закрыть текущую сессию (после ротации IP или обрыва соединения).

        Держать keep-alive поверх смены выходного IP нельзя: установленный TCP
        остаётся на старом — прожжённом — адресе, и ротация становится
        фикцией. Оборванное соединение переиспользовать тоже бессмысленно.
        """
        session, self._session = self._session, None
        self._session_proxy = None
        if session is not None:
            with suppress(Exception):
                session.close()

    def close(self) -> None:
        """Освободить соединение. Идемпотентна — тулзы зовут её в ``finally``."""
        self._drop_session()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def get(self, url: str, max_attempts: int | None = None) -> Any:
        """GET с ротацией IP до чистого. Возвращает 200-ответ или бросает RuntimeError.

        ``max_attempts`` переопределяет лимит попыток для этого вызова — нужно
        для редирект-хопа на одноразовый токен (см. ``fetch_catalog``), где
        долбить один и тот же URL до общего потолка бессмысленно.

        Если обычная ротация IP исчерпана, а блок держится (см. живой прогон
        2026-07-20: одна и та же подсеть мобильного прокси даёт 403 на любом
        адресе внутри неё), пробуем один раз эскалировать прокси — сменить
        физическую точку/оператора через `Proxy.escalate()` (см. `MpsApiProxy`)
        — и повторить полный круг попыток заново. Не более одного раза за
        вызов, чтобы не тратить время бесконечно.
        """
        limit = max_attempts if max_attempts is not None else self.max_attempts
        escalated = False
        while True:
            resp, attempt = self._attempt_get(url, limit)
            if resp is not None:
                return resp
            if self._out_of_budget():
                break
            if escalated:
                break
            escalated = True
            if not getattr(self.proxy, "escalate", lambda: False)():
                break
            log.warning(
                "исчерпаны %s попыток ротации — эскалировал прокси (смена "
                "региона/оператора) и пробую заново",
                limit,
            )
        via = "прокси не задан" if self.proxy.httpx_proxy() is None else "через прокси"
        if self._out_of_budget():
            raise RuntimeError(
                f"не удалось получить {url}: исчерпан бюджет времени "
                f"{self.budget:.0f}с за {attempt} попыток (блокировки IP, {via}). "
                "Увеличьте AVITO_REQUEST_BUDGET либо дайте чистый RU-прокси "
                "(AVITO_PROXY, AVITO_PROXY_CHANGE_URL)"
            )
        raise RuntimeError(
            f"не удалось получить {url} за {attempt} из {limit} попыток "
            f"(блокировки IP, {via}). Нужен чистый RU-прокси: "
            "задайте AVITO_PROXY и AVITO_PROXY_CHANGE_URL"
        )

    def _attempt_get(self, url: str, limit: int) -> tuple[Any | None, int]:
        """Один полный круг попыток без эскалации. Возвращает ``(resp, attempt)``;
        ``resp is None`` — круг исчерпан без чистого ответа."""
        with timed("cookies.get", logger=log):
            cookies = self.cookies.get() if self.cookies else None
        blocks = 0
        tried_without_cookies = False
        # Читается после цикла в сообщении об отказе: limit <= 0 (законное
        # "не ротировать" из env) не должен давать UnboundLocalError вместо
        # контрактного RuntimeError.
        attempt = 0
        for attempt in range(1, limit + 1):
            if self._out_of_budget():
                # Бюджет кончился — следующая попытка всё равно не успеет
                # ничего отдать, а стоит она платной ротации и минуты сна.
                log.warning("бюджет времени исчерпан — прекращаю попытки")
                return None, attempt
            proxy_url = self.proxy.httpx_proxy()
            log.info(
                "GET %s (попытка %s/%s, прокси %s)",
                url,
                attempt,
                limit,
                mask_proxy(proxy_url) if proxy_url else "нет",
            )
            try:
                with timed("http.request", logger=log, attempt=attempt):
                    resp = self._get_session().get(
                        url, cookies=cookies, timeout=self.timeout, allow_redirects=True
                    )
            except CurlError as exc:
                # Соединение оборвалось — переиспользовать его нельзя.
                self._drop_session()
                if isinstance(exc, ValueError):
                    # Битый конфиг (невалидный AVITO_PROXY/схема URL) — не
                    # сетевая случайность, ротация IP её не лечит. Отдаём
                    # исходную ошибку сразу, а не тратим попытки/маскируем
                    # под общий "нужен чистый RU-прокси".
                    raise
                log.warning("транспортная ошибка (%s) — ротирую IP", exc)
                # Здесь, в отличие от блокировки, цикл НЕ обрывается при
                # rotated=False: таймаут/обрыв TCP лечится повтором, а не
                # сменой IP, и без прокси (rotate() всегда False) отказ с
                # первой же сетевой случайности был бы регрессией.
                blocks, _ = self._rotate_and_backoff(attempt, limit, blocks)
                continue
            log.info("ответ %s на попытке %s", resp.status_code, attempt)
            if self.cookies:
                self.cookies.update(resp)
            if resp.status_code in self.block_codes:
                if attempt >= limit:
                    # Круг закончен: лечить блокировку под несуществующую
                    # следующую попытку незачем — для spfa это платный вызов.
                    break
                # Лечение по возрастанию цены: куки ~0.6 с против ~5 с на смену
                # выходного адреса, а помогают они примерно одинаково часто
                # (см. test_http_recovery_ladder). Раньше дорогое средство шло
                # на КАЖДУЮ блокировку: profile дал proxy.rotate=96.9s×19 при
                # 19.9 с полезной работы.
                # Самое дешёвое лекарство — вообще без кук: выгоревшие куки не
                # просто бесполезны, они портят запрос, который без них
                # проходит (замер 2026-07-20: без кук 200 за 0.77 с, с ними
                # 403). Не стоит ни денег, ни секунд, ни ротации — и НЕ считается
                # ступенью лестницы: иначе сдвигает её чётность и вытесняет
                # обновление кук (в живом прогоне cookies.refresh исчез совсем).
                if cookies and not tried_without_cookies:
                    log.warning("блокировка %s — пробую без кук", resp.status_code)
                    tried_without_cookies = True
                    cookies = None
                    continue
                blocks += 1
                healed = False
                if blocks % _COOKIE_REFRESH_EVERY != 0 and self.cookies:
                    log.warning("блокировка %s — обновляю куки", resp.status_code)
                    with timed("cookies.refresh", logger=log):
                        healed = self.cookies.handle_block()
                    if not healed:
                        # Лечить куки нечем (провайдер `own`, троттлинг spfa) —
                        # повтор с теми же куками и тем же адресом ушёл бы в тот
                        # же 403, просто за счёт бюджета.
                        log.info("куки обновить не удалось — меняю выходной адрес")
                if not healed:
                    log.warning(
                        "блокировка %s — меняю выходной адрес", resp.status_code
                    )
                    _, rotated = self._rotate_and_backoff(
                        attempt, limit, blocks - 1, status=resp.status_code
                    )
                    if not rotated:
                        break
                cookies = self.cookies.get() if self.cookies else None
                # Комбинация сменилась — бесплатную попытку без кук имеет смысл
                # повторить и на ней.
                tried_without_cookies = False
                continue
            return resp, attempt
        # Без прокси менять нечего: NoProxy.rotate() — заглушка, все попытки идут
        # с одного IP. Круг исчерпан без чистого ответа — решение (эскалировать
        # или сдаться) принимает вызывающий (`get()`).
        return None, attempt

    def _rotate_and_backoff(
        self, attempt: int, limit: int, blocks: int, status: int | None = None
    ) -> tuple[int, bool]:
        """Сменить IP и выждать нарастающий backoff. Общий путь для кода-блокировки
        и транспортной ошибки — раньше был продублирован в обеих ветках ``get()``.

        Экспоненциальный backoff с потолком: первая блокировка часто случайна,
        а на десятой частые повторы только злят антибот. После последней
        попытки не спим — всё равно сдаёмся.

        Время самой ротации засчитывается в паузу. Живой прогон 2026-07-20:
        смена IP через кабинет занимает 3.6–4.3 с — это уже пауза, и ждать
        сверх неё полный интервал незачем, тем более что после смены выходного
        адреса «остывать» нужно не нам, а прежнему IP. В той же сводке видно
        цену прежнего поведения: ``backoff.sleep=54.0s`` против
        ``http.request=4.3s`` полезной работы.

        Возвращает ``(blocks, rotated)``. ``rotated=False`` — сменить выходной
        IP нечем (``NoProxy``/``ServerProxy``, исчерпанный ``ProxyPool``,
        отказавший кабинет мобильного прокси): повторять с того же адреса
        бессмысленно, а полный бюджет попыток с backoff — это ~15 минут
        ожидания заведомо той же блокировки. В этом случае не спим вовсе.
        """
        if attempt >= limit:
            # Круг закончен: следующей попытки не будет, а дальше либо
            # эскалация (она сама меняет точку выхода), либо отказ. Ротация
            # здесь — 3.6–4.3 с в никуда. rotated=True, чтобы вызывающий
            # отличал «менять нечем» (break) от «просто закончились попытки».
            return blocks + 1, True
        started = time.monotonic()
        with timed("proxy.rotate", logger=log):
            rotated = self.proxy.rotate()
        if rotated:
            # Соединение осталось бы на прежнем выходном IP — см. _drop_session.
            self._drop_session()
        # Смена звена цепочки транспортов уже дала другой выходной адрес —
        # «остывать» нечему, а пауза перед прямым соединением (0.63 с на
        # запрос) была бы в разы дороже самой работы.
        instant = rotated and getattr(self.proxy, "rotation_was_instant", False)
        # Ждать имеет смысл только когда нас притормаживают по частоте (429).
        # 403/401 — бан адреса или кук: сон его не снимает, лечит смена
        # комбинации, которая уже произошла выше.
        rate_limited = status in _RATE_LIMIT_CODES
        if rotated and not instant and rate_limited and attempt < limit:
            delay = min(self.wait_after_rotate * (2**blocks), self.backoff_cap)
            remaining = max(0.0, delay - (time.monotonic() - started))
            # Спать дольше остатка бюджета бессмысленно: проснёмся уже за его
            # пределами и всё равно сдадимся, просто позже.
            remaining = min(remaining, max(0.0, self._remaining()))
            # Отдельной фазой: в сводке видно, сколько времени тулза именно
            # СПАЛА — это то, что оптимизируется настройкой, а не кодом.
            with timed("backoff.sleep", logger=log, seconds=f"{remaining:.1f}"):
                _sleep(remaining)
        return blocks + 1, rotated


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
    """Забрать страницу каталога, следуя SSR-редиректу (см. :func:`_follow`)."""
    kind, payload, _ = _follow(client, url, max_redirects, max_token_refreshes)
    return kind, payload


def fetch_page(
    client: HttpClient,
    url: str,
    max_redirects: int = 3,
    max_token_refreshes: int = 3,
):  # noqa: ANN201 — тип ответа принадлежит curl_cffi
    """Забрать произвольную страницу, следуя SSR-редиректу, и вернуть ответ.

    Страница объявления классифицируется не как каталог (``catalog.items`` на
    ней нет), поэтому ``fetch_catalog`` для неё не годится — но редирект на
    канонический URL Avito делает и для карточки товара. Без хопа парсер
    получает страницу-редирект и не находит объявление.

    Raises:
        RuntimeError: редирект-цепочка не сошлась (исчерпаны бюджеты).
    """
    kind, _, resp = _follow(client, url, max_redirects, max_token_refreshes)
    if resp is None:
        raise RuntimeError(explain_status(kind))
    return resp


def _follow(
    client: HttpClient,
    url: str,
    max_redirects: int,
    max_token_refreshes: int,
) -> tuple[PageKind, Any, Any]:
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

    Возвращает ``(kind, payload, resp)`` — результат ``classify`` плюс сам
    ответ (нужен вызывающим, которые разбирают HTML сами, а не каталог).
    При исчерпании бюджета — ``(REDIRECT_LOOP, None, None)``.
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
                return PageKind.REDIRECT_LOOP, None, None
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
                return PageKind.REDIRECT_LOOP, None, None
            current_url = to_absolute_avito_url(payload)
            on_redirect_hop = True
            continue
        return kind, payload, resp
