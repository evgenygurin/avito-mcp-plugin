# avito-mcp-plugin — контекст для Gemini

Переносимый плагин: skills + MCP-сервер (FastMCP v3) для работы с Avito.

Полные инструкции для агентов — в [`CLAUDE.md`](CLAUDE.md) (общий гайд).
Ключевое:

- **Guardrails:** не реализовывать «лобовой» обход капчи (ст. 272 УК), не
  собирать ПДн для перепродажи (152-ФЗ), не копировать существенную долю БД
  (ст. 1334 ГК). См. [`docs/avito-legal.md`](docs/avito-legal.md).
- **Skills** меняются по методологии `writing-skills` (`description` = когда, не что).
- **MCP-сервер** — в [`server/`](server/README.md), `uv`, тесты `Client(mcp)`.
- Секреты — только через env, не хардкодить.

Архитектура: [`docs/architecture.md`](docs/architecture.md).
