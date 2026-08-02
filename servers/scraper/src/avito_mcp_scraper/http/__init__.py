"""HTTP-слой скрапинга (curl_cffi, rotate-until-clean, follow-редирект)."""

from .client import HttpClient, fetch_catalog

__all__ = ["HttpClient", "fetch_catalog"]
