"""Настройка логирования сервера: stderr всегда, файл — по желанию.

Зачем отдельный модуль. Пакет писал диагностику через ``logging`` с самого
начала (попытки GET, коды ответов, ротации IP, номера страниц), но никто её не
видел: root-логгер без хендлеров пропускает наружу только WARNING+ через
``logging.lastResort``, а весь полезный лист — INFO. Из-за этого «тулза
выполняется долго» было неотличимо от «тулза зависла».

Два правила, из которых следует всё остальное:

* **stdout занят протоколом.** При stdio-транспорте по нему идёт JSON-RPC —
  любая посторонняя строка ломает сессию. Логи уходят только в stderr (и в файл).
* **Логи не роняют сервер.** Недоступный ``AVITO_LOG_FILE`` — предупреждение в
  stderr, а не отказ старта.

Логгер MCP-клиента (``ctx.info`` и родня) — отдельный канал, он идёт в клиент
по протоколу; здесь настраивается серверная сторона.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

#: Корень пространства имён пакета: настраиваем его, а не root — чужая
#: конфигурация root (в т.ч. хендлер на stdout) не должна нас касаться.
PACKAGE_LOGGER = "avito_mcp_server"

_DEFAULT_LEVEL = "INFO"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
#: Файл лога режется по 5 МБ: долгий прогон с DEBUG пишет мегабайты, а лог в
#: домашнем каталоге не должен расти безгранично.
_FILE_MAX_BYTES = 5 * 1024 * 1024
_FILE_BACKUPS = 3

#: Метка на хендлерах, поставленных этим модулем: повторный вызов
#: ``setup_logging`` переставляет свои и не трогает чужие (напр. из тестов).
_MARK = "_avito_mcp_handler"


def _level_from_env() -> int:
    """Уровень из ``LOG_LEVEL``; опечатка не повод падать на старте."""
    raw = os.getenv("LOG_LEVEL", "").strip().upper() or _DEFAULT_LEVEL
    level = logging.getLevelNamesMapping().get(raw)
    return level if level is not None else logging.INFO


def _file_handler(path: Path, formatter: logging.Formatter) -> logging.Handler | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            path, maxBytes=_FILE_MAX_BYTES, backupCount=_FILE_BACKUPS, encoding="utf-8"
        )
    except OSError as exc:
        # Пишем в stderr напрямую: логгер в этот момент ещё собирается.
        print(f"не удалось открыть файл лога {path}: {exc}", file=sys.stderr)
        return None
    handler.setFormatter(formatter)
    setattr(handler, _MARK, True)
    return handler


def setup_logging() -> logging.Logger:
    """Настроить логгер пакета по окружению и вернуть его.

    Идемпотентна: повторный вызов заменяет собственные хендлеры, а не
    добавляет вторую копию каждой строки (``server.py`` может быть и
    импортирован, и запущен как точка входа).

    Окружение:
        LOG_LEVEL: ``DEBUG``/``INFO``/``WARNING``/… (дефолт ``INFO``).
        AVITO_LOG_FILE: путь к файлу лога; без него пишем только в stderr.
    """
    logger = logging.getLogger(PACKAGE_LOGGER)
    logger.setLevel(_level_from_env())
    # Иначе строка выйдет дважды, если root настроен кем-то ещё.
    logger.propagate = False

    for handler in [h for h in logger.handlers if getattr(h, _MARK, False)]:
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    stream = logging.StreamHandler(stream=sys.stderr)
    stream.setFormatter(formatter)
    setattr(stream, _MARK, True)
    logger.addHandler(stream)

    raw_path = os.getenv("AVITO_LOG_FILE", "").strip()
    if raw_path:
        file_handler = _file_handler(Path(raw_path).expanduser(), formatter)
        if file_handler is not None:
            logger.addHandler(file_handler)

    return logger
