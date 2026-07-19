"""Встроенное SSR-состояние страницы: извлечение и классификация.

Avito отдаёт состояние в теге ``<script type="mime/invalid" data-mfe-state="true">``
(html-escaped JSON). Внутри — ``loaderData.data``: либо каталог (``catalog.items``),
либо состояние SSR-редиректа на канонический URL категории (``redirected``/``url``).
"""

from __future__ import annotations

import html as html_lib
import json
from enum import StrEnum
from typing import Any

from bs4 import BeautifulSoup, SoupStrainer

# Фильтр НА ЭТАПЕ ПАРСИНГА (а не итерация по уже готовому дереву): страница
# каталога — это ~1МБ HTML ради ОДНОГО нужного тега. SoupStrainer не даёт
# парсеру строить узлы вне фильтра вовсе — замер на реальной фикстуре (29
# script-тегов) показал ~19x меньше пикового потребления памяти и ~30% меньше
# CPU-времени по сравнению с полным деревом + soup.select() после него.
_STATE_SCRIPT = SoupStrainer(
    "script", attrs={"type": "mime/invalid", "data-mfe-state": "true"}
)


class PageKind(StrEnum):
    """Что именно вернула страница.

    ``StrEnum``, а не голые строки: значения по-прежнему сравниваются с
    литералами (``kind == "ok"``) и сериализуются как есть, но опечатка в
    ветвлении теперь ловится типами, а не тихо уводит в ветку «неизвестный
    статус».
    """

    OK = "ok"
    REDIRECT = "redirect"
    FIREWALL = "firewall"
    SOFTBLOCK = "softblock"
    NOJSON = "nojson"
    REDIRECT_LOOP = "redirect_loop"


#: Результат классификации: вид страницы + полезная нагрузка под этот вид
#: (каталог для ``OK``, URL для ``REDIRECT``, ``None`` для остальных).
PageResult = tuple[PageKind, Any]

# Маркеры страницы «Доступ ограничен: проблема с IP» (Qrator firewall + капча).
_FIREWALL_MARKERS = ("firewall-container", "js-firewall-form", "firewallCaptcha")

_STATUS_HINTS: dict[PageKind, str] = {
    PageKind.FIREWALL: (
        "Avito заблокировал IP (страница «проблема с IP» с капчей). Капчу не решаем: "
        "нужен чистый RU-прокси — задайте AVITO_PROXY и AVITO_PROXY_CHANGE_URL"
    ),
    PageKind.SOFTBLOCK: (
        "страница отдалась без каталога (поведенческий флаг) — обычно помогает "
        "смена IP или свежие куки"
    ),
    PageKind.NOJSON: "во встроенном состоянии страницы нет данных каталога",
    PageKind.REDIRECT: "страница вернула SSR-редирект вместо каталога",
    PageKind.REDIRECT_LOOP: (
        "страница зациклилась на редиректах или не отдала свежий токен"
    ),
}


def find_json_on_page(html_code: str) -> dict[str, Any]:
    """Найти встроенный SSR-JSON и вернуть ``loaderData.data`` (или ``{}``)."""
    soup = BeautifulSoup(html_code, "html.parser", parse_only=_STATE_SCRIPT)
    for script in soup.find_all("script"):
        if "sandbox" in script.text:
            continue
        try:
            data = json.loads(html_lib.unescape(script.text))
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and data.get("i18n", {}).get("hasMessages"):
            loader = data.get("loaderData", {})
            if isinstance(loader, dict) and isinstance(loader.get("data"), dict):
                return loader["data"]
    return {}


def classify(html_code: str) -> PageResult:
    """Классифицировать страницу.

    Возвращает одно из:
    - ``(OK, catalog)`` — есть каталог с объявлениями;
    - ``(REDIRECT, url)`` — SSR-редирект на канонический URL;
    - ``(FIREWALL, None)`` — страница блокировки по IP с капчей;
    - ``(SOFTBLOCK, None)`` — 200, но каталога нет (поведенческий флаг/заглушка);
    - ``(NOJSON, None)`` — встроенного состояния не найдено.
    """
    data = find_json_on_page(html_code)
    if not data:
        if any(marker in html_code for marker in _FIREWALL_MARKERS):
            return PageKind.FIREWALL, None
        return PageKind.NOJSON, None
    if data.get("redirected") and data.get("url"):
        return PageKind.REDIRECT, data["url"]
    catalog = data.get("catalog")
    if isinstance(catalog, dict) and catalog.get("items"):
        return PageKind.OK, catalog
    return PageKind.SOFTBLOCK, None


def explain_status(kind: str) -> str:
    """Человекочитаемый диагноз для статуса ``classify`` — для сообщений тулз."""
    hint = _STATUS_HINTS.get(PageKind(kind)) if kind in set(PageKind) else None
    return (
        f"{hint} (статус: {kind})"
        if hint
        else f"страница не отдала каталог (статус: {kind})"
    )
