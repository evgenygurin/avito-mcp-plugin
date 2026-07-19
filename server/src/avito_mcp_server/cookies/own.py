"""Провайдер заранее заданных пользовательских кук."""

from __future__ import annotations

from .base import CookiesProvider


class OwnCookiesProvider(CookiesProvider):
    def __init__(self, cookies: dict) -> None:
        self._cookies = dict(cookies or {})

    def get(self) -> dict:
        return self._cookies

    def handle_block(self) -> None:
        # Свои куки автоматически не обновляемы — блок разруливается ротацией IP.
        return
