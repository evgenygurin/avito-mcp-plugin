"""Детерминированные утилиты (без сети, без побочных эффектов)."""

from __future__ import annotations


def extract_listing_id(value: str) -> int:
    """Извлечь числовой id объявления Avito из URL или «голого» id.

    Поддерживает desktop-URL (``.../slug_1234567890``), мобильный API-URL
    (``.../items/1234567890``) и строку из одних цифр. Query-string
    игнорируется.

    Raises:
        ValueError: если id извлечь не удалось.
    """
    path = value.split("?", 1)[0].rstrip("/")
    if not path:
        raise ValueError("пустая строка — id не найден")

    last_segment = path.rsplit("/", 1)[-1]
    candidate = last_segment.rsplit("_", 1)[-1]
    if candidate.isdigit():
        return int(candidate)

    raise ValueError(f"не удалось извлечь id объявления из: {value!r}")
