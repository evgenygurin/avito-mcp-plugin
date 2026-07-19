"""MCP-тулза отправки уведомлений в Telegram / VK."""

from __future__ import annotations

import os

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from ..models import NotificationResult
from ..notifications.sender import NotificationChannel, get_notifier
from ..notifications.sender import send_notification as do_send
from .execution import run_blocking


def _resolve_targets(targets: list[str] | None, env_var: str) -> list[str]:
    """Явные ``targets`` побеждают; иначе — список из env (через запятую)."""
    if targets:
        return targets
    return [t.strip() for t in os.getenv(env_var, "").split(",") if t.strip()]


def register(mcp: FastMCP) -> None:
    """Зарегистрировать тулзу уведомлений на инстансе FastMCP."""

    @mcp.tool(
        annotations=ToolAnnotations(destructiveHint=True, openWorldHint=True),
    )
    async def send_notification(
        message: str,
        ctx: Context,
        channel: NotificationChannel = "telegram",
        targets: list[str] | None = None,
    ) -> NotificationResult:
        """Отправить уведомление в Telegram или VK о найденных объявлениях.

        Use when нужно оповестить пользователя о результатах парсинга
        (новые объявления, снижение цены). Требует ``AVITO_TG_TOKEN`` /
        ``AVITO_TG_CHAT_IDS`` для Telegram или ``AVITO_VK_TOKEN`` /
        ``AVITO_VK_USER_IDS`` для VK. ``targets`` переопределяет список
        получателей из env.
        """
        await ctx.info(f"send_notification: {channel}")

        def _run() -> NotificationResult:
            # Какие env-переменные читать, знает сам канал — тулза не хранит
            # копию соответствия «канал → токен/адресаты».
            notifier = get_notifier(channel)
            detail, sent, actual_targets = do_send(
                channel=channel,
                message=message,
                token=os.getenv(notifier.token_env),
                targets=_resolve_targets(targets, notifier.targets_env),
            )
            return NotificationResult(
                channel=channel, sent=sent, targets=actual_targets, detail=detail
            )

        return await run_blocking(_run, failure="не удалось отправить уведомление")
