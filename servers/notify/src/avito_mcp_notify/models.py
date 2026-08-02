"""Модели уведомлений avito-mcp-notify."""

from __future__ import annotations

from pydantic import BaseModel, Field


class NotificationResult(BaseModel):
    """Результат отправки уведомления.

    ``sent`` — дошло ли ВСЕМ адресатам; частичная доставка даёт ``sent=false``
    и непустой ``failed``, иначе отвалившийся получатель виден только человеку
    в ``detail``, а агент считает рассылку успешной.
    """

    channel: str
    sent: bool
    targets: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    detail: str = ""
