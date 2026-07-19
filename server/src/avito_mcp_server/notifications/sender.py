"""Отправка уведомлений: Telegram / VK."""

from __future__ import annotations

from collections.abc import Callable

import httpx

# (адресат, доставлено, детали) — итог по каждому получателю.
_Delivery = tuple[str, bool, str]


def _deliver(targets: list[str], send_one: Callable[[str], None]) -> list[_Delivery]:
    """Отправить каждому адресату независимо — сбой одного не отменяет остальных."""
    results: list[_Delivery] = []
    for target in targets:
        try:
            send_one(target)
        except Exception as exc:  # noqa: BLE001 — сбой одного не отменяет остальных
            results.append((target, False, str(exc)))
        else:
            results.append((target, True, "ok"))
    return results


def _send_telegram(token: str, chat_ids: list[str], text: str) -> list[_Delivery]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    def _send_one(chat_id: str) -> None:
        httpx.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
            trust_env=False,
        ).raise_for_status()

    return _deliver(chat_ids, _send_one)


def _send_vk(token: str, user_ids: list[str], text: str) -> list[_Delivery]:
    url = "https://api.vk.com/method/messages.send"

    def _send_one(user_id: str) -> None:
        resp = httpx.post(
            url,
            data={
                "user_id": user_id,
                "message": text,
                "access_token": token,
                "v": "5.199",
                "random_id": 0,
            },
            timeout=15,
            trust_env=False,
        )
        resp.raise_for_status()
        # VK отвечает 200 и кладёт ошибку в тело — по статусу её не видно.
        error = resp.json().get("error")
        if error:
            raise RuntimeError(
                f"{error.get('error_msg', error)} (код {error.get('error_code')})"
            )

    return _deliver(user_ids, _send_one)


def send_notification(
    channel: str,
    message: str,
    tg_token: str | None = None,
    tg_chat_ids: list[str] | None = None,
    vk_token: str | None = None,
    vk_user_ids: list[str] | None = None,
) -> tuple[str, bool, list[str]]:
    """Отправить уведомление в Telegram или VK.

    Returns:
        (detail, sent, targets) — результат отправки.
    """
    if channel == "telegram":
        if not tg_token:
            raise ValueError("AVITO_TG_TOKEN не задан")
        if not tg_chat_ids:
            raise ValueError("AVITO_TG_CHAT_IDS не задан")
        return _summarize(_send_telegram(tg_token, tg_chat_ids, message))
    elif channel == "vk":
        if not vk_token:
            raise ValueError("AVITO_VK_TOKEN не задан")
        if not vk_user_ids:
            raise ValueError("AVITO_VK_USER_IDS не задан")
        return _summarize(_send_vk(vk_token, vk_user_ids, message))
    raise ValueError(f"неподдерживаемый канал: {channel!r} (telegram|vk)")


def _summarize(results: list[_Delivery]) -> tuple[str, bool, list[str]]:
    """Свести доставку по адресатам: что дошло, что нет.

    Частичный успех — не полный провал: адресаты, которым сообщение ушло, не
    должны получать его повторно из-за сбоя на соседе.
    """
    delivered = [target for target, ok, _ in results if ok]
    failed = [(target, detail) for target, ok, detail in results if not ok]
    if not failed:
        return ("ok", True, delivered)
    problems = "; ".join(f"{target}: {detail}" for target, detail in failed)
    if not delivered:
        raise RuntimeError(f"не доставлено ни одному адресату — {problems}")
    return (
        f"доставлено {len(delivered)} из {len(results)}; ошибки — {problems}",
        True,
        delivered,
    )
