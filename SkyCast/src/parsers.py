"""
Асинхронные парсеры данных с различных источников для SkyCast.

Источники данных:
1. METAR (aviationweather.gov) - публичный стабильный API
2. WMO/WWIS (worldweather.wmo.int) - публичный JSON формат
3. Open-Meteo (open-meteo.com) - бесплатный API без ключа
4. RainViewer (api.rainviewer.com) - радарные тайлы
"""
from __future__ import annotations

import re
import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

import httpx

from config import (
    RUSSIAN_ICAO_CODES,
    WEATHER_INTENSITY_MAP,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

log = logging.getLogger("skycast.parsers")

HEADERS = {"User-Agent": USER_AGENT}

# --------------------------------------------------------------------------
# 1. METAR (aviationweather.gov) - основной источник для аэродромов
# --------------------------------------------------------------------------

_METAR_PATTERNS = [
    # Грозы и ливни (максимальная интенсивность)
    (re.compile(r"\bTSRA\b"), 5.0),
    (re.compile(r"\bTS\b"), 5.0),
    (re.compile(r"\+TSRA\b"), 5.0),
    # Сильные ливни
    (re.compile(r"\+SHRA\b"), 4.0),
    (re.compile(r"\+SHSN\b"), 4.0),
    (re.compile(r"\bSHRA\b"), 3.5),
    (re.compile(r"\bSHSN\b"), 3.0),
    # Сильные осадки
    (re.compile(r"\+RA\b"), 3.5),
    (re.compile(r"\+SN\b"), 3.5),
    # Умеренные осадки
    (re.compile(r"\bRA\b"), 2.5),
    (re.compile(r"\bSN\b"), 2.5),
    (re.compile(r"\bDZ\b"), 1.5),
    # Слабые осадки
    (re.compile(r"-RA\b"), 1.5),
    (re.compile(r"-SN\b"), 1.5),
    (re.compile(r"-DZ\b"), 1.0),
    (re.compile(r"-SHRA\b"), 2.0),
]


def _intensity_from_metar_text(raw: str) -> float:
    """Парсит METAR текст и возвращает интенсивность осадков 0-5."""
    if not raw:
        return 0.0
    best = 0.0
    for pattern, weight in _METAR_PATTERNS:
        if pattern.search(raw):
            best = max(best, weight)
    return best


async def fetch_metar(client: httpx.AsyncClient, icao_codes: list[str]) -> list[dict]:
    """Забирает METAR для списка ICAO-кодов и возвращает [{lat, lon, intensity, source}]."""
    results: list[dict] = []
    
    # Разбиваем на пакеты по 50 кодов (ограничение API)
    batch_size = 50
    batches = [icao_codes[i:i + batch_size] for i in range(0, len(icao_codes), batch_size)]
    
    for batch in batches:
        ids_param = ",".join(batch)
        url = f"https://aviationweather.gov/api/data/metar?ids={ids_param}&format=json"
        
        try:
            resp = await client.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException as exc:
            log.warning("METAR: таймаут запроса для пакета %s: %s", batch, exc)
            continue
        except httpx.HTTPStatusError as exc:
            log.warning("METAR: HTTP ошибка %s: %s", exc.response.status_code, exc)
            continue
        except Exception as exc:
            log.warning("METAR: запрос не удался: %s", exc)
            continue

        for station in data if isinstance(data, list) else []:
            try:
                lat = station.get("lat")
                lon = station.get("lon")
                raw = station.get("rawOb") or station.get("metar") or ""
                wx = station.get("wxString") or ""
                
                if lat is None or lon is None:
                    continue
                    
                intensity = _intensity_from_metar_text(raw) or _intensity_from_metar_text(wx)
                
                results.append({
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "intensity": float(intensity),
                    "source": "METAR",
                    "station": station.get("icaoId", "UNKNOWN"),
                    "timestamp": datetime.utcnow().isoformat(),
                })
            except Exception as exc:
                log.debug("METAR: пропущена станция из-за ошибки парсинга: %s", exc)
                continue
    
    log.info("METAR: получено %d станций из %d запрошенных", len(results), len(icao_codes))
    return results


# --------------------------------------------------------------------------
# 2. WMO / WWIS - всемирная сеть метеостанций
# --------------------------------------------------------------------------

async def fetch_wmo_russia_city_ids(client: httpx.AsyncClient) -> list[tuple[str, str]]:
    """Скачивает реестр городов WMO и отбирает станции РФ/СНГ."""
    url = "https://worldweather.wmo.int/en/json/full_city_list.txt"
    out: list[tuple[str, str]] = []
    
    try:
        resp = await client.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("WMO: не удалось скачать реестр городов: %s", exc)
        return out

    members = data.get("member") if isinstance(data, dict) else data
    if not isinstance(members, list):
        log.warning("WMO: неожиданный формат реестра городов")
        return out

    target_countries = ["russia", "kazakhstan", "belarus", "ukraine", "uzbekistan"]
    
    for entry in members:
        try:
            country = str(entry.get("countryName") or entry.get("country") or "")
            if any(c in country.lower() for c in target_countries):
                city_id = str(entry.get("cityId") or entry.get("city_id"))
                city_name = str(entry.get("cityName") or entry.get("city") or "")
                if city_id and city_id != "None":
                    out.append((city_id, city_name))
        except Exception:
            continue
    
    log.info("WMO: найдено %d станций в целевых странах", len(out))
    return out


def _intensity_from_wmo_text(text: str) -> float:
    """Преобразует текстовое описание погоды WMO в интенсивность 0-5."""
    if not text:
        return 0.0
    t = text.lower()
    best = 0.0
    for phrase, weight in WEATHER_INTENSITY_MAP.items():
        if phrase in t:
            best = max(best, weight)
    return best


async def fetch_wmo_station(client: httpx.AsyncClient, city_id: str, city_name: str) -> Optional[dict]:
    """Запрашивает данные по конкретной станции WMO."""
    url = f"https://worldweather.wmo.int/en/json/{city_id}_en.json"
    
    try:
        resp = await client.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.debug("WMO: станция %s (%s) недоступна: %s", city_name, city_id, exc)
        return None

    try:
        city_block = data.get("city", {})
        lat = city_block.get("cityLatitude") or city_block.get("latitude")
        lon = city_block.get("cityLongitude") or city_block.get("longitude")
        present = city_block.get("presentWeather") or city_block.get("weatherDescription") or ""
        
        if lat is None or lon is None:
            return None
            
        intensity = _intensity_from_wmo_text(str(present))
        
        return {
            "latitude": float(lat),
            "longitude": float(lon),
            "intensity": intensity,
            "source": "WMO",
            "station": city_name,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        log.debug("WMO: ошибка парсинга станции %s: %s", city_name, exc)
        return None


async def fetch_wmo_all(client: httpx.AsyncClient, limit: Optional[int] = 200) -> list[dict]:
    """Запрашивает данные со всех станций WMO в РФ/СНГ."""
    stations = await fetch_wmo_russia_city_ids(client)
    
    if limit:
        stations = stations[:limit]
    if not stations:
        return []
    
    # Запрашиваем параллельно, но с ограничением одновременных соединений
    semaphore = asyncio.Semaphore(20)
    
    async def fetch_with_semaphore(cid, name):
        async with semaphore:
            return await fetch_wmo_station(client, cid, name)
    
    tasks = [fetch_with_semaphore(cid, name) for cid, name in stations]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    
    valid_results = [r for r in results if r]
    log.info("WMO: получено %d станций из %d запрошенных", len(valid_results), len(stations))
    return valid_results


# --------------------------------------------------------------------------
# 3. Open-Meteo - бесплатный API без ключа (дополнительный источник)
# --------------------------------------------------------------------------

async def fetch_openmeteo_stations(client: httpx.AsyncClient, bbox: tuple) -> list[dict]:
    """
    Запрашивает ближайшие метеостанции Open-Meteo в заданном bbox.
    Open-Meteo предоставляет бесплатный API без необходимости ключа.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": center_lat,
        "longitude": center_lon,
        "hourly": "weathercode",
        "past_days": "0",
        "timezone": "UTC",
    }
    
    results = []
    try:
        resp = await client.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        
        # Open-Meteo возвращает данные для точки, используем их
        if "hourly" in data and "weathercode" in data["hourly"]:
            codes = data["hourly"]["weathercode"]
            latest_code = codes[-1] if codes else 0
            
            # Преобразуем WMO код погоды в интенсивность
            intensity = _wmo_code_to_intensity(latest_code)
            
            results.append({
                "latitude": center_lat,
                "longitude": center_lon,
                "intensity": intensity,
                "source": "OpenMeteo",
                "station": "OpenMeteo_Grid",
                "timestamp": datetime.utcnow().isoformat(),
            })
    except Exception as exc:
        log.debug("Open-Meteo: ошибка запроса: %s", exc)
    
    return results


def _wmo_code_to_intensity(code: int) -> float:
    """Преобразует WMO код погоды в интенсивность осадков."""
    if code == 0:
        return 0.0  # Ясно
    elif code <= 3:
        return 0.0  # Облачно
    elif code <= 5:
        return 0.5  # Туман
    elif code <= 20:
        return 0.0  # Дымка, пыль
    elif code <= 48:
        return 0.5  # Иней, туман с инеем
    elif code <= 57:
        return 1.0  # Морось
    elif code <= 67:
        return 2.0  # Дождь
    elif code <= 77:
        return 2.5  # Снег/крупа
    elif code <= 80:
        return 2.5  # Ливневый дождь
    elif code <= 85:
        return 3.0  # Ливневой снег
    elif code <= 96:
        return 4.0  # Сильный ливень
    elif code <= 99:
        return 5.0  # Гроза с градом
    return 0.0


# --------------------------------------------------------------------------
# 4. RainViewer - радарные тайлы (для подложки и калибровки)
# --------------------------------------------------------------------------

async def fetch_rainviewer_metadata(client: httpx.AsyncClient) -> Optional[dict]:
    """Запрашивает метаданные доступных радарных слоёв RainViewer."""
    url = "https://api.rainviewer.com/public/weather-maps.json"
    
    try:
        resp = await client.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data
    except Exception as exc:
        log.warning("RainViewer: запрос не удался: %s", exc)
        return None


async def fetch_rainviewer_latest_tile_template(client: httpx.AsyncClient) -> Optional[str]:
    """Возвращает URL-шаблон последнего радарного слоя RainViewer."""
    metadata = await fetch_rainviewer_metadata(client)
    
    if not metadata:
        return None

    try:
        radar = metadata.get("radar", {})
        frames = radar.get("past") or radar.get("nowcast") or []
        
        if not frames:
            return None
            
        last = frames[-1]
        path = last.get("path")
        
        if not path:
            return None
            
        template = f"https://tilecache.rainviewer.com{path}/256/{{z}}/{{x}}/{{y}}/1/1_1.png"
        log.info("RainViewer: получен шаблон тайлов: %s", template)
        return template
    except Exception as exc:
        log.debug("RainViewer: ошибка парсинга метаданных: %s", exc)
        return None


# --------------------------------------------------------------------------
# 5. NWS/NOAA GRIB данные (для глобального покрытия)
# --------------------------------------------------------------------------

async def fetch_noaa_grib_data(client: httpx.AsyncClient, bbox: tuple) -> list[dict]:
    """
    Запрашивает данные о_precipitation из NOAA GFS модели.
    Это дополнительный источник для регионов без наземных станций.
    """
    # Используем открытый API NOAA для получения данных
    # Примечание: это упрощённая реализация, в production нужно использовать
    # специализированные библиотеки для работы с GRIB
    
    results = []
    log.debug("NOAA GFS: запрос данных для bbox %s", bbox)
    
    # В реальной реализации здесь был бы запрос к NOMADS или AWS Open Data
    # Для бесплатного хостинга используем упрощённый подход
    
    return results
