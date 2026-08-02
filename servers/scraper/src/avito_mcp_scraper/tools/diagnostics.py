"""MCP-тулза диагностики прокси/кук."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from ..config import build_http_client, rotate_wait
from ..cookies.base import CookiesProvider
from ..http.client import HttpClient, fetch_catalog
from ..models import ProxyHealth, ProxyProbe
from ..parser import PageKind, explain_status
from ..progress import report
from ..proxies.proxy import ProxyPool, ServerProxy
from ..timing import current_timings, track
from ..utils import mask_proxy
from .execution import run_blocking

log = logging.getLogger(__name__)

_PROBE_URL = "https://www.avito.ru/nizhniy_novgorod/kvartiry/prodam"
#: Сколько адресов пула проверяется одновременно. Адреса независимы, а проба —
#: сетевой запрос до 20 с: последовательный обход пула из двух десятков адресов
#: упирался в собственный ``timeout=180`` тулзы. Потолок нужен, чтобы пул на
#: сотню адресов не поднимал сотню потоков и сотню соединений к провайдеру.
MAX_PROBE_WORKERS = 8
#: Потолок времени на пробу одного адреса. Диагностика обязана ответить, а не
#: уйти в полный rotate-until-clean: `asyncio.to_thread` не отменяется по
#: `timeout` тулзы, и поток продолжал бы жечь платные ротации уже после того,
#: как клиент получил отказ (живой прогон 2026-07-20).
PROBE_BUDGET = 30.0
# Диагностика должна отвечать быстро и предсказуемо, а не крутить полный
# rotate-until-clean. 3 попытки с тем же прокси хватает, чтобы отличить
# "прокси мёртв" от случайной блокировки; жёсткая граница — PROBE_BUDGET.
_SINGLE_PROXY_PROBE_ATTEMPTS = 3


#: Проба одного адреса: ``(клиент, url) -> (жив, пояснение)``. Аргументом, а не
#: импортом, — чтобы тест мог подменить сетевую часть, не трогая параллелизм.
Probe = Callable[[HttpClient, str], tuple[bool, str]]


def probe_pool(
    urls: Sequence[str],
    cookies: CookiesProvider | None,
    probe_url: str,
    probe: Probe,
) -> list[ProxyProbe]:
    """Проверить адреса пула параллельно, сохранив порядок из конфига.

    Каждый адрес проверяется ОТДЕЛЬНЫМ клиентом со статическим прокси: общий
    пул ротирует внутри запроса, и ответ пришёл бы с другого адреса — «живым»
    оказался бы мёртвый. Одна попытка на адрес: диагностика отвечает быстро, а
    не крутит rotate-until-clean.

    Порядок результатов — как в конфиге, а не как пришли ответы: иначе
    «третий адрес мёртв» не сопоставить с настройкой.
    """
    if not urls:
        return []
    # ThreadPoolExecutor не переносит contextvars — копилку замеров передаём в
    # рабочий поток явно, иначе фазы проб не попадут в сводку тулзы.
    timings = current_timings()

    def _one(raw: str) -> ProxyProbe:
        client = HttpClient(
            proxy=ServerProxy(raw),
            cookies=cookies,
            max_attempts=1,
            budget=PROBE_BUDGET,
        )
        try:
            if timings is not None:
                with track(timings):
                    ok, detail = probe(client, probe_url)
            else:
                ok, detail = probe(client, probe_url)
        except Exception as exc:  # noqa: BLE001 — мёртвый адрес не ошибка тулзы
            ok, detail = False, f"ошибка: {exc}"
        finally:
            client.close()
        log.info("прокси %s: %s", mask_proxy(raw), "живой" if ok else detail)
        return ProxyProbe(proxy=mask_proxy(raw), ok=ok, detail=detail)

    workers = min(MAX_PROBE_WORKERS, len(urls))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # map сохраняет порядок входа и поднимает исключения на итерации —
        # их ловит _one, чтобы один мёртвый адрес не терял остальные.
        probes = list(pool.map(_one, urls))
    for index, item in enumerate(probes, start=1):
        report(index, len(probes), f"прокси {item.proxy}")
    return probes


def register(mcp: FastMCP) -> None:
    """Зарегистрировать диагностическую тулзу на инстансе FastMCP."""

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
        # Каждый адрес пула проверяется max_attempts=1 (см. _run ниже) — не
        # полный rotate-until-clean, но пул из десятков адресов всё же может
        # набежать на сумму таймаутов; 180с — щедрый запас для типичного пула.
        timeout=180,
    )
    async def check_proxy_health(
        ctx: Context,
        probe_url: str = _PROBE_URL,
    ) -> ProxyHealth:
        """Проверить связку прокси+кук: пробует получить каталог, сообщает исход.

        Use when надо убедиться, что антибот пробивается (прокси/куки рабочие),
        до массового парсинга. Возвращает конфиг и результат пробного запроса; при
        блокировке НЕ бросает ошибку — это валидный диагноз (``ok=false``).
        """
        await ctx.info(f"check_proxy_health: {probe_url}")

        def _probe(client: HttpClient, url: str) -> tuple[bool, str]:
            try:
                kind, _ = fetch_catalog(client, url)
            except Exception as exc:  # noqa: BLE001 — блокировка не ошибка тулзы
                return False, f"ошибка: {exc}"
            ok = kind == PageKind.OK
            return ok, ("каталог получен" if ok else explain_status(kind))

        def _run() -> ProxyHealth:
            # Собранный клиент здесь нужен только как источник фактической
            # связки прокси/кук — сами пробы делают отдельные клиенты, но
            # закрыть его всё равно обязаны (см. HttpClient.close).
            client = build_http_client()
            client.close()
            proxy_type = type(client.proxy).__name__
            # Что РЕАЛЬНО собралось, а не что написано в env: диагностика
            # обязана показывать фактическую связку, иначе тулза, созданная
            # искать проблему с куками, сама её маскирует.
            provider = (
                type(client.cookies).__name__
                if client.cookies is not None
                else "нет (куки отключены)"
            )
            probes: list[ProxyProbe] = []

            pool = client.proxy if isinstance(client.proxy, ProxyPool) else None
            if pool is not None:
                # С пулом важен не общий вердикт, а какие именно адреса живы.
                probes = probe_pool(pool.urls, client.cookies, probe_url, _probe)
                alive = [p for p in probes if p.ok]
                return ProxyHealth(
                    ok=bool(alive),
                    cookie_provider=provider,
                    proxy_type=proxy_type,
                    detail=f"живых адресов: {len(alive)} из {len(probes)}",
                    probes=probes,
                )

            # Без пула — тоже не полный rotate-until-clean: поток внутри
            # asyncio.to_thread не отменяется по timeout тулзы и продолжал бы
            # жечь платные ротации уже после отказа клиенту. Отсюда и
            # PROBE_BUDGET — жёсткая граница, которую соблюдает сам движок.
            with HttpClient(
                proxy=client.proxy,
                cookies=client.cookies,
                max_attempts=_SINGLE_PROXY_PROBE_ATTEMPTS,
                wait_after_rotate=rotate_wait(),
                budget=PROBE_BUDGET,
            ) as probe_client:
                ok, detail = _probe(probe_client, probe_url)
            return ProxyHealth(
                ok=ok,
                cookie_provider=provider,
                proxy_type=proxy_type,
                detail=detail,
            )

        # build_http_client() может бросить ДО входа в _probe (напр. ValueError
        # "пул прокси пуст") — та же ToolError-граница, что и у остальных тулз.
        return await run_blocking(
            _run,
            failure="не удалось проверить прокси",
            operation="check_proxy_health",
            ctx=ctx,
        )
