"""MCP-тулза отправки уведомлений в Telegram / VK."""

from __future__ import annotations

import asyncio
import os

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError

from ..models import NotificationResult
from ..notifications.sender import send_notification as do_send


def _resolve_targets(targets: list[str] | None, env_var: str) -> list[str]:
    """Явные ``targets`` побеждают; иначе — список из env (через запятую)."""
    if targets:
        return targets
    return [t.strip() for t in os.getenv(env_var, "").split(",") if t.strip()]


def register(mcp: FastMCP) -> None:
    """Зарегистрировать тулзу уведомлений на инстансе FastMCP."""

    @mcp.tool
    async def send_notification(
        message: str,
        ctx: Context,
        channel: str = "telegram",
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
            tg_token = os.getenv("AVITO_TG_TOKEN")
            tg_chat_ids = _resolve_targets(targets, "AVITO_TG_CHAT_IDS")
            vk_token = os.getenv("AVITO_VK_TOKEN")
            vk_user_ids = _resolve_targets(targets, "AVITO_VK_USER_IDS")

            detail, sent, actual_targets = do_send(
                channel=channel,
                message=message,
                tg_token=tg_token,
                tg_chat_ids=tg_chat_ids if channel == "telegram" else None,
                vk_token=vk_token,
                vk_user_ids=vk_user_ids if channel == "vk" else None,
            )
            return NotificationResult(
                channel=channel, sent=sent, targets=actual_targets, detail=detail
            )

        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:
            raise ToolError(f"не удалось отправить уведомление: {exc}") from exc
