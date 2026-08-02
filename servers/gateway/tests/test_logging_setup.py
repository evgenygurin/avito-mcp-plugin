"""Тесты настройки логирования (logging_setup.py).

Логи движка парсинга — единственный способ понять, ПОЧЕМУ тулза выполняется
долго. До этого модуля они молча терялись: root-логгер без хендлеров отдаёт
только WARNING+ через lastResort, а весь диагностический лог парсера — INFO.
"""

from __future__ import annotations

import logging

import pytest

from avito_mcp_server.logging_setup import PACKAGE_LOGGER, setup_logging


@pytest.fixture(autouse=True)
def _clean_logger():
    """Каждый тест начинает с чистого логгера пакета и возвращает его как был."""
    logger = logging.getLogger(PACKAGE_LOGGER)
    saved_handlers = logger.handlers[:]
    saved_level = logger.level
    saved_propagate = logger.propagate
    logger.handlers = []
    yield logger
    for handler in logger.handlers:
        handler.close()
    logger.handlers = saved_handlers
    logger.setLevel(saved_level)
    logger.propagate = saved_propagate


def test_info_reaches_stderr_not_stdout(_clean_logger, capsys) -> None:
    # stdout при stdio-транспорте занят JSON-RPC: лог туда ломает протокол.
    setup_logging()
    logging.getLogger("avito_mcp_server.http.client").info("ротирую IP")

    captured = capsys.readouterr()
    assert "ротирую IP" in captured.err
    assert captured.out == ""


def test_level_from_env(_clean_logger, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    setup_logging()
    logging.getLogger("avito_mcp_server.parser").debug("страница разобрана")

    assert "страница разобрана" in capsys.readouterr().err


def test_default_level_is_info(_clean_logger, monkeypatch, capsys) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    setup_logging()
    logging.getLogger("avito_mcp_server.parser").debug("шумный отладочный лог")

    assert capsys.readouterr().err == ""


def test_invalid_level_falls_back_to_info(_clean_logger, monkeypatch, capsys) -> None:
    # Опечатка в LOG_LEVEL не должна ронять сервер на старте.
    monkeypatch.setenv("LOG_LEVEL", "ОЧЕНЬ_ПОДРОБНО")
    setup_logging()
    logging.getLogger("avito_mcp_server.parser").info("работаю")

    assert "работаю" in capsys.readouterr().err


def test_is_idempotent(_clean_logger, capsys) -> None:
    # server.py импортируется и как модуль, и как точка входа: двойная
    # настройка не должна дублировать каждую строку лога.
    setup_logging()
    setup_logging()
    logging.getLogger("avito_mcp_server.parser").info("однажды")

    assert capsys.readouterr().err.count("однажды") == 1


def test_does_not_propagate_to_root(_clean_logger) -> None:
    # Иначе чужая конфигурация root (в т.ч. хендлер на stdout) продублирует лог.
    setup_logging()
    assert logging.getLogger(PACKAGE_LOGGER).propagate is False


def test_writes_to_file_when_requested(_clean_logger, monkeypatch, tmp_path) -> None:
    log_file = tmp_path / "nested" / "avito.log"
    monkeypatch.setenv("AVITO_LOG_FILE", str(log_file))
    setup_logging()
    logging.getLogger("avito_mcp_server.http.client").info("GET страницы 1")

    assert "GET страницы 1" in log_file.read_text(encoding="utf-8")


def test_unwritable_log_file_does_not_break_server(
    _clean_logger, monkeypatch, tmp_path, capsys
) -> None:
    # Логи — вспомогательная функция: недоступный путь не повод не стартовать.
    blocker = tmp_path / "file"
    blocker.write_text("не каталог")
    monkeypatch.setenv("AVITO_LOG_FILE", str(blocker / "avito.log"))
    setup_logging()
    logging.getLogger("avito_mcp_server.parser").info("работаю дальше")

    assert "работаю дальше" in capsys.readouterr().err


def test_record_carries_timestamp_and_module(_clean_logger, capsys) -> None:
    # Без имени модуля и времени лог бесполезен для поиска медленной фазы.
    setup_logging()
    logging.getLogger("avito_mcp_server.http.client").info("ответ 200")

    line = capsys.readouterr().err
    assert "avito_mcp_server.http.client" in line
    # Время пишется в начале строки — ISO-подобная дата с дефисами.
    assert line[:4].isdigit()
