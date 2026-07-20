"""Эскалация мобильного прокси через API mobileproxy.space (mpsapi.com).

Простая ротация IP (`MobileProxy.rotate()`) меняет адрес в пределах той же
физической точки — не спасает, если под подозрением Qrator вся подсеть
региона/оператора (см. `avito-scraping-findings` в памяти проекта: подсеть
Билайн/Москва давала 18/18 блоков, МегаФон/Самара пробивался). `escalate()`
делает то, что раньше приходилось делать вручную в личном кабинете —
переключает физическую точку (`change_equipment`) на не-московскую с
достаточным числом свободных портов у настроенного оператора.
"""

from __future__ import annotations

import logging

import httpx

from .proxy import MobileProxy

log = logging.getLogger(__name__)

API_URL = "https://mpsapi.com/api.html"

# Точки в Москве/Московской области чаще всего прожжены интенсивным тестовым
# трафиком (эмпирика сессий 2026-07): исключаем их из кандидатов на эскалацию.
_MOSCOW_MARKERS = ("Москва", "Московская область", "МО,")


class MpsApiProxy(MobileProxy):
    """Мобильный прокси со сменой оборудования (регион/оператор) при упорных блоках.

    `rotate()` наследуется от `MobileProxy` (смена IP на той же точке).
    `escalate()` — смена физической точки на не-московскую через
    `change_equipment`, когда одной ротации IP мало.
    """

    def __init__(
        self,
        url: str,
        change_url: str,
        api_token: str,
        proxy_id: str,
        operator: str = "megafone",
        timeout: float = 20.0,
    ) -> None:
        super().__init__(url, change_url, timeout=timeout)
        self.api_token = api_token
        self.proxy_id = proxy_id
        self.operator = operator
        # Не повторяем уже испробованные в этом прогоне точки — иначе
        # эскалация может вернуть ту же прожжённую точку заново.
        self._tried_geoids: set[str] = set()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}"}

    def _pick_clean_geoid(self) -> str | None:
        try:
            resp = httpx.get(
                API_URL,
                params={
                    "command": "get_geo_operator_list",
                    "type": "0",
                    "proxy_id": self.proxy_id,
                },
                headers=self._headers(),
                timeout=self.timeout,
                trust_env=False,
            )
        except httpx.HTTPError as exc:
            log.warning("не удалось получить список гео/операторов: %s", exc)
            return None
        if resp.status_code != 200:
            log.warning("список гео/операторов вернул статус %s", resp.status_code)
            return None
        try:
            geo_list = resp.json().get("geo_operator_list", {})
        except ValueError:
            log.warning("список гео/операторов вернул некорректный JSON")
            return None

        candidates = [
            (geoid, info)
            for geoid, info in geo_list.items()
            if geoid not in self._tried_geoids
            and info.get("id_country") == "1"
            and self.operator in info.get("count_free", {})
            and not any(m in info.get("geo_caption", "") for m in _MOSCOW_MARKERS)
        ]
        if not candidates:
            return None
        # Больше свободных портов у оператора — меньше риска сразу упереться
        # в занятость конкретной точки.
        best_geoid, _ = max(
            candidates, key=lambda item: int(item[1]["count_free"][self.operator])
        )
        return best_geoid

    def escalate(self) -> bool:
        geoid = self._pick_clean_geoid()
        if geoid is None:
            log.warning(
                "эскалация прокси: нет свободной не-московской точки оператора %s",
                self.operator,
            )
            return False
        try:
            resp = httpx.get(
                API_URL,
                params={
                    "command": "change_equipment",
                    "proxy_id": self.proxy_id,
                    "geoid": geoid,
                    "operator": self.operator,
                    "check_after_change": "true",
                },
                headers=self._headers(),
                timeout=self.timeout,
                trust_env=False,
            )
        except httpx.HTTPError as exc:
            log.warning("эскалация прокси (смена оборудования) не удалась: %s", exc)
            return False
        self._tried_geoids.add(geoid)
        if resp.status_code != 200:
            log.warning("смена оборудования вернула статус %s", resp.status_code)
            return False
        log.warning("прокси эскалирован на новую точку geoid=%s", geoid)
        return True
