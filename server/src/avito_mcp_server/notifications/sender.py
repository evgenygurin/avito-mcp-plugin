"""Отправка уведомлений: Telegram / VK.

Канал — стратегия (``Notifier``): валидация обязательных настроек, отправка
одному адресату и разбор ответа API живут в одном классе, а общий обход
адресатов и сведение результата — в этом модуле. Новый канал добавляется
реализацией + записью в ``_NOTIFIERS``, без ветвлений в точке входа.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import httpx

# Канал уведомления — контракт MCP-схемы тулзы send_notification.
NotificationChannel = Literal["telegram", "vk"]

# (адресат, доставлено, детали) — итог по каждому получателю.
_Delivery = tuple[str, bool, str]

_TIMEOUT = 15.0


# Ниже этой длины «секрет» — не секрет, а фрагмент, который встречается в
# обычном тексте (в тестах токен бывает односимвольным). Слепая замена такой
# подстроки изуродовала бы диагностику: «User au***horiza***ion failed».
_MIN_SECRET_LEN = 8


def _describe_failure(exc: Exception, secret: str) -> str:
    """Текст ошибки доставки БЕЗ учётных данных.

    Telegram кладёт токен прямо в путь URL, а ``httpx.HTTPStatusError`` печатает
    URL целиком — без этого протухший токен уехал бы в ответ тулзы, в контекст
    модели и в логи MCP-клиента. Поэтому для HTTP-ошибок сообщение строим сами
    (статус + хост), а не берём готовую строку исключения.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} от {exc.request.url.host}"
    text = str(exc) or type(exc).__name__
    if secret and len(secret) >= _MIN_SECRET_LEN:
        text = text.replace(secret, "***")
    return text


def _deliver(
    targets: list[str], send_one: Callable[[str], None], secret: str = ""
) -> list[_Delivery]:
    """Отправить каждому адресату независимо — сбой одного не отменяет остальных."""
    results: list[_Delivery] = []
    for target in targets:
        try:
            send_one(target)
        except Exception as exc:  # noqa: BLE001 — сбой одного не отменяет остальных
            results.append((target, False, _describe_failure(exc, secret)))
        else:
            results.append((target, True, "ok"))
    return results


class Notifier(ABC):
    """Канал доставки уведомлений."""

    #: Имена env-переменных для сообщения о недостающей настройке.
    token_env: str
    targets_env: str

    def send(self, token: str | None, targets: list[str], text: str) -> list[_Delivery]:
        """Проверить настройки и разослать сообщение всем адресатам.

        Один ``httpx.Client`` на всю рассылку: N адресатов иначе — N отдельных
        TCP+TLS рукопожатий к одному и тому же хосту вместо переиспользования
        соединения.
        """
        if not token:
            raise ValueError(f"{self.token_env} не задан")
        if not targets:
            raise ValueError(f"{self.targets_env} не задан")
        with httpx.Client(timeout=_TIMEOUT, trust_env=False) as client:
            return _deliver(
                targets,
                lambda target: self._send_one(client, token, target, text),
                secret=token,
            )

    @abstractmethod
    def _send_one(
        self, client: httpx.Client, token: str, target: str, text: str
    ) -> None:
        """Отправить сообщение одному адресату; ошибка → исключение."""


class TelegramNotifier(Notifier):
    token_env = "AVITO_TG_TOKEN"
    targets_env = "AVITO_TG_CHAT_IDS"

    def _send_one(
        self, client: httpx.Client, token: str, target: str, text: str
    ) -> None:
        client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": target, "text": text, "parse_mode": "HTML"},
        ).raise_for_status()


class VkNotifier(Notifier):
    token_env = "AVITO_VK_TOKEN"
    targets_env = "AVITO_VK_USER_IDS"

    API_VERSION = "5.199"

    def _send_one(
        self, client: httpx.Client, token: str, target: str, text: str
    ) -> None:
        resp = client.post(
            "https://api.vk.com/method/messages.send",
            data={
                "user_id": target,
                "message": text,
                "access_token": token,
                "v": self.API_VERSION,
                "random_id": 0,
            },
        )
        resp.raise_for_status()
        # VK отвечает 200 и кладёт ошибку в тело — по статусу её не видно.
        error = resp.json().get("error")
        if error:
            raise RuntimeError(
                f"{error.get('error_msg', error)} (код {error.get('error_code')})"
            )


_NOTIFIERS: dict[str, Notifier] = {
    "telegram": TelegramNotifier(),
    "vk": VkNotifier(),
}


def get_notifier(channel: str) -> Notifier:
    """Стратегия канала.

    Raises:
        ValueError: канал не поддерживается.
    """
    notifier = _NOTIFIERS.get(channel)
    if notifier is None:
        supported = "|".join(_NOTIFIERS)
        raise ValueError(f"неподдерживаемый канал: {channel!r} ({supported})")
    return notifier


@dataclass(frozen=True)
class DeliveryReport:
    """Итог рассылки по адресатам."""

    detail: str
    delivered: list[str]
    failed: list[str]

    @property
    def sent(self) -> bool:
        """Дошло ли ВСЕМ адресатам.

        Именно «всем», а не «хоть кому-то»: агент проверяет булево поле, и при
        ``sent=True`` с молча отвалившимся адресатом мониторинг неделями
        отправляет уведомления в никуда, а сигнала об этом нет нигде, кроме
        прозаического ``detail``.
        """
        return not self.failed


def send_notification(
    channel: str,
    message: str,
    token: str | None = None,
    targets: list[str] | None = None,
) -> DeliveryReport:
    """Отправить уведомление в выбранный канал.

    Имена env-переменных знает сам канал (``Notifier.token_env`` /
    ``targets_env``), поэтому здесь один токен и один список адресатов вместо
    пары параметров на каждый поддерживаемый мессенджер.

    Raises:
        ValueError: канал не поддерживается либо не заданы токен/адресаты.
        RuntimeError: не доставлено ни одному адресату.
    """
    notifier = get_notifier(channel)
    return _summarize(notifier.send(token, targets or [], message))


def _summarize(results: list[_Delivery]) -> DeliveryReport:
    """Свести доставку по адресатам: что дошло, что нет.

    Частичный успех — не полный провал: адресаты, которым сообщение ушло, не
    должны получать его повторно из-за сбоя на соседе. Но и успехом он не
    считается — провалившиеся адресаты видны в ``failed``.
    """
    delivered = [target for target, ok, _ in results if ok]
    failures = [(target, detail) for target, ok, detail in results if not ok]
    if not failures:
        return DeliveryReport(detail="ok", delivered=delivered, failed=[])
    problems = "; ".join(f"{target}: {detail}" for target, detail in failures)
    if not delivered:
        raise RuntimeError(f"не доставлено ни одному адресату — {problems}")
    return DeliveryReport(
        detail=f"доставлено {len(delivered)} из {len(results)}; ошибки — {problems}",
        delivered=delivered,
        failed=[target for target, _ in failures],
    )
