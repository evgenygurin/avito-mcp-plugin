"""Экспорт объявлений: xlsx (openpyxl) / json / csv."""

from __future__ import annotations

import csv
import json
import re
from io import BytesIO, StringIO
from pathlib import Path

from ..models import Listing


# Символы, на которых openpyxl бросает IllegalCharacterError; в описаниях
# объявлений они встречаются регулярно и роняли весь экспорт.
_ILLEGAL_XLSX = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]")

# Текст объявления пишет продавец: значение, начинающееся с этих символов,
# Excel/LibreOffice трактуют как формулу и выполняют при открытии файла.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Потолок для inline-возврата xlsx (base64), ~64 КБ: дальше файл обязан идти
# на диск, иначе ответ тулзы вытеснит контекст модели.
_MAX_INLINE_XLSX = 64 * 1024


def _safe_text(value: str | None) -> str:
    """Обезвредить текст из объявления перед записью в файл."""
    if not value:
        return ""
    cleaned = _ILLEGAL_XLSX.sub("", value)
    if cleaned.startswith(_FORMULA_PREFIXES):
        # Апостроф заставляет табличный редактор трактовать значение как текст.
        return "'" + cleaned
    return cleaned


def _listings_to_rows(listings: list[Listing]) -> list[list[object]]:
    """Строки для таблицы: числа остаются числами, текст обезврежен."""
    return [
        [
            item.id,
            _safe_text(item.title),
            item.price,
            _safe_text(item.address),
            _safe_text(item.url),
            item.published_at,
            item.views,
            _safe_text(item.description),
        ]
        for item in listings
    ]


_HEADER = [
    "id",
    "title",
    "price",
    "address",
    "url",
    "published_at",
    "views",
    "description",
]


def to_xlsx_bytes(listings: list[Listing]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(_HEADER)
    for row in _listings_to_rows(listings):
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_json_str(listings: list[Listing]) -> str:
    return json.dumps(
        [item.model_dump() for item in listings],
        ensure_ascii=False,
        indent=2,
    )


def to_csv_str(listings: list[Listing]) -> str:
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(_HEADER)
    writer.writerows(_listings_to_rows(listings))
    return buf.getvalue()


def export_listings(
    listings: list[Listing],
    fmt: str,
    path: str | None = None,
) -> tuple[str, str | None]:
    """Экспортировать объявления в заданном формате.

    Returns:
        (content, path) — если path задан, пишет в файл и возвращает путь;
        иначе возвращает содержимое как строку (json/csv) или base64 (xlsx).
    """
    if fmt == "xlsx":
        data = to_xlsx_bytes(listings)
        if path:
            Path(path).write_bytes(data)
            return ("", path)
        import base64

        encoded = base64.b64encode(data).decode()
        # Base64 бинарника возвращается прямо в ответ MCP-тулзы и попадает в
        # контекст модели: крупная выгрузка вытеснила бы полезные данные.
        if len(encoded) > _MAX_INLINE_XLSX:
            raise ValueError(
                f"xlsx на {len(listings)} объявлений слишком велик для ответа "
                f"({len(encoded) // 1024} КБ base64) — укажите path, "
                "чтобы сохранить файл на диск"
            )
        return (encoded, None)
    elif fmt == "csv":
        content = to_csv_str(listings)
    elif fmt == "json":
        content = to_json_str(listings)
    else:
        raise ValueError(f"неподдерживаемый формат: {fmt!r} (xlsx|json|csv)")

    if path:
        Path(path).write_text(content, encoding="utf-8")
        return ("", path)
    return (content, None)
