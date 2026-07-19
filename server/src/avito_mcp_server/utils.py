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


def mask_proxy(url: str) -> str:
    """Убрать логин/пароль из строки прокси — наружу отдаём только host:port.

    Живёт рядом с прочими детерминированными утилитами, а не среди Pydantic-моделей:
    ответ тулзы и запись в ``proxy_cooldown`` не должны нести учётные данные.
    """
    return url.rsplit("@", 1)[-1] if url else url


def is_absolute_url(value: str) -> bool:
    """Строка уже является абсолютным http(s)-URL?"""
    return value.startswith(("http://", "https://"))


def to_listing_url(id_or_url: str) -> str:
    """URL страницы объявления по URL или голому id.

    Пользовательский ввод тулз (``get_listing``) допускает и то, и другое:
    ссылку оставляем как есть, из id строим канонический мобильный путь.

    Raises:
        ValueError: если id извлечь не удалось.
    """
    if is_absolute_url(id_or_url):
        return id_or_url
    return f"https://www.avito.ru/items/{extract_listing_id(id_or_url)}"


def to_absolute_avito_url(location: str) -> str:
    """Достроить относительный путь Avito (``/город/категория``) до полного URL.

    Уже абсолютные URL (``http://``/``https://``) возвращаются без изменений —
    Avito отдаёт и то, и другое в разных полях (``pager.next``, редирект
    ``loaderData.data.url``), и вызывающему коду не нужно об этом думать.
    """
    return location if is_absolute_url(location) else f"https://www.avito.ru{location}"
