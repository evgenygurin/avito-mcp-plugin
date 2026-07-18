# avito-mcp-plugin — контекст для Gemini

Переносимый плагин: skills + MCP-сервер (FastMCP v3) для работы с Avito. Цель —
полнофункциональный парсер каталога Avito: парсинг и мониторинг публичных
объявлений.

Полные инструкции для агентов — в [`CLAUDE.md`](CLAUDE.md) (общий гайд).
Ключевое:

- **Статус:** движок парсинга (куки → rotate-until-clean → curl_cffi →
  извлечение JSON каталога) валидирован живьём, но не портирован в код. Все
  7 MCP-тулз — в статусе «🔜 план». Канон дизайна —
  [`docs/superpowers/specs/2026-07-18-avito-parser-design.md`](docs/superpowers/specs/2026-07-18-avito-parser-design.md).
- **Исключение:** `parse_phone` (сбор телефонов продавцов) сознательно не
  реализуется — ПДн третьих лиц в промышленном масштабе.
- **Skills** меняются по методологии `writing-skills` (`description` = когда, не что).
- **MCP-сервер** — в [`server/`](server/README.md), `uv`, тесты `Client(mcp)`.
- Секреты (`SPFA_API_KEY`, прокси-креды, токены Telegram/VK) — только через
  env, не хардкодить.

Архитектура: [`docs/architecture.md`](docs/architecture.md).
