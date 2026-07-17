# Релиз и публикация

Процесс выпуска новой версии плагина и публикации MCP-сервера в PyPI.

> CI (GitHub Actions) пока не настроен — шаги выполняются вручную. Когда появится
> workflow, публикация по тегу автоматизируется через PyPI Trusted Publishing.

## 1. Версии (SemVer)

Версия должна совпадать в **пяти** местах:

- `.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json` (`plugins[0].version`)
- `server/pyproject.toml` (`project.version`)
- `gemini-extension.json`
- `.cursor-plugin/plugin.json`

После bump — проверить синхронность:

```bash
python3 scripts/check_versions.py     # exit 0 = синхронны
```

## 2. Changelog

Перенести изменения из `## [Unreleased]` в новую секцию `## [X.Y.Z] — YYYY-MM-DD`
в [`CHANGELOG.md`](../CHANGELOG.md). Обновить ссылки сравнения внизу файла.

## 3. Проверки

```bash
cd server
uv sync --dev
uv run ruff check .
uv run mypy src
uv run pytest -q
```

Плюс валидация плагина:

```bash
claude plugin validate ./
```

## 4. Сборка и публикация MCP-сервера

```bash
cd server
uv build            # sdist + wheel в server/dist/
uv publish          # публикация в PyPI (нужен токен или Trusted Publishing)
```

Для TestPyPI: `uv publish --publish-url https://test.pypi.org/legacy/`.

> **Секреты не коммитить.** Токен PyPI — через переменные окружения/CI-secret,
> не в репозитории.

## 5. Переключение MCP-конфига на PyPI

После первой публикации в `[`.mcp.json`](../.mcp.json)` и примерах
[`examples/mcp-configs/`](../examples/mcp-configs/) можно заменить запуск из git
на пакет PyPI:

```jsonc
// было (из git):
{ "command": "uvx", "args": ["--from", "git+https://…#subdirectory=server", "avito-mcp-server"] }
// стало (из PyPI):
{ "command": "uvx", "args": ["avito-mcp-server"] }
```

## 6. Тег

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

## 7. Маркетплейс

После публикации пользователи ставят плагин:

```bash
/plugin marketplace add evgenygurin/avito-mcp-plugin
/plugin install avito-mcp-plugin@avito-mcp-marketplace
```
