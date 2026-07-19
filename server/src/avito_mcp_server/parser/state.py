"""Встроенное SSR-состояние страницы: извлечение и классификация.

Avito отдаёт состояние в теге ``<script type="mime/invalid" data-mfe-state="true">``
(html-escaped JSON). Внутри — ``loaderData.data``: каталог (``catalog.items``),
состояние SSR-редиректа на канонический URL категории (``redirected``/``url``)
либо карточка объявления (``item``/``itemFull``/``listing``) — последнюю разбирает
:mod:`.mapping`, но состояние со страницы извлекает тоже этот модуль.
"""

from __future__ import annotations

import html as html_lib
import json
from enum import StrEnum
from typing import Any

from bs4 import BeautifulSoup, SoupStrainer

# Фильтр НА ЭТАПЕ ПАРСИНГА (а не итерация по уже готовому дереву): страница
# каталога — это ~1МБ HTML ради одного-двух нужных тегов. SoupStrainer не даёт
# парсеру строить узлы вне фильтра вовсе — замер на фикстуре
# tests/fixtures/redirect_stub.html (29 script-тегов) показал 29.6МБ → 1.6МБ
# пикового потребления памяти и ~30% меньше CPU-времени по сравнению с полным
# деревом + soup.select() после него. Воспроизводится tracemalloc'ом на ней же.
_STATE_SCRIPT = SoupStrainer(
    "script", attrs={"type": "mime/invalid", "data-mfe-state": "true"}
)


class PageKind(StrEnum):
    """Что именно вернула страница.

    ``StrEnum``, а не голые строки: значения по-прежнему сравниваются с
    литералами (``kind == "ok"``) и сериализуются как есть. Ветвиться следует
    по членам (``PageKind.OK``) — там опечатку ловит проверка типов; сравнение
    с литералом остаётся законным и типами НЕ проверяется.
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

# Ключи — члены PageKind, но тип объявлен строковым: статус приходит и как
# enum, и как обычная строка (моки тестов, старые вызовы) — StrEnum делает
# оба варианта одним ключом.
_STATUS_HINTS: dict[str, str] = {
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
    """Человекочитаемый диагноз статуса страницы — для сообщений тулз.

    Принимает статус и от ``classify``, и от ``fetch_catalog`` (тот добавляет
    ``REDIRECT_LOOP``). Ключи словаря — ``StrEnum``, поэтому обычная строка
    находит запись без приведения типа.
    """
    hint = _STATUS_HINTS.get(kind)
    return (
        f"{hint} (статус: {kind})"
        if hint
        else f"страница не отдала каталог (статус: {kind})"
    )
