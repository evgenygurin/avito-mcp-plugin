"""Провайдеры кук для доступа к Avito (spfa / own)."""

from .base import CookiesProvider
from .factory import build_cookies_provider

__all__ = ["CookiesProvider", "build_cookies_provider"]
