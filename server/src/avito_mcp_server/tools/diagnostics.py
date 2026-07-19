"""MCP-тулза диагностики прокси/кук."""

from __future__ import annotations

import asyncio
import logging
import os

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from ..config import DEFAULT_COOKIE_PROVIDER, build_http_client
from ..http.client import HttpClient
from ..http.client import fetch_catalog
from ..models import ProxyHealth, ProxyProbe, mask_proxy
from ..parser import explain_status
from ..proxies.proxy import ProxyPool, ServerProxy

log = logging.getLogger(__name__)

_PROBE_URL = "https://www.avito.ru/nizhniy_novgorod/kvartiry/prodam"


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
        provider = os.getenv("AVITO_COOKIE_PROVIDER", DEFAULT_COOKIE_PROVIDER)
        await ctx.info(f"check_proxy_health: {probe_url}")

        def _probe(client: HttpClient, url: str) -> tuple[bool, str]:
            try:
                kind, _ = fetch_catalog(client, url)
            except Exception as exc:  # noqa: BLE001 — блокировка не ошибка тулзы
                return False, f"ошибка: {exc}"
            return (kind == "ok"), (
                "каталог получен" if kind == "ok" else explain_status(kind)
            )

        def _run() -> ProxyHealth:
            client = build_http_client()
            proxy_type = type(client.proxy).__name__
            probes: list[ProxyProbe] = []

            pool = client.proxy if isinstance(client.proxy, ProxyPool) else None
            if pool is not None:
                # С пулом важен не общий вердикт, а какие именно адреса живы.
                # Каждый адрес проверяем ОТДЕЛЬНЫМ клиентом со статическим прокси:
                # общий пул ротирует внутри запроса, и ответ пришёл бы с другого
                # адреса — «живым» оказался бы мёртвый. Одна попытка на адрес:
                # диагностика отвечает быстро, а не крутит rotate-until-clean.
                for raw in pool.urls:
                    probe_client = HttpClient(
                        proxy=ServerProxy(raw),
                        cookies=client.cookies,
                        max_attempts=1,
                    )
                    ok, detail = _probe(probe_client, probe_url)
                    probes.append(
                        ProxyProbe(proxy=mask_proxy(raw), ok=ok, detail=detail)
                    )
                    log.info(
                        "прокси %s: %s", mask_proxy(raw), "живой" if ok else detail
                    )
                alive = [p for p in probes if p.ok]
                return ProxyHealth(
                    ok=bool(alive),
                    cookie_provider=provider,
                    proxy_type=proxy_type,
                    detail=f"живых адресов: {len(alive)} из {len(probes)}",
                    probes=probes,
                )

            ok, detail = _probe(client, probe_url)
            return ProxyHealth(
                ok=ok,
                cookie_provider=provider,
                proxy_type=proxy_type,
                detail=detail,
            )

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:
            # build_http_client() может бросить ДО входа в _probe (напр.
            # ValueError "пул прокси пуст") — единая ToolError-граница, как у
            # остальных 6 тулз, вместо белой вороны в контракте ошибок.
            raise ToolError(f"не удалось проверить прокси: {exc}") from exc
