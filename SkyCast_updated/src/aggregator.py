"""
Агрегация данных со всех источников в единый DataFrame и дедупликация.
Использует scipy.spatial.cKDTree для быстрой пространственной дедупликации.
"""
from __future__ import annotations

import logging
import math
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
from scipy.spatial import cKDTree
import httpx

from config import RUSSIAN_ICAO_CODES, REQUEST_TIMEOUT, CACHE_DIR, CACHE_TTL_SECONDS
import parsers

log = logging.getLogger("skycast.aggregator")

DEDUP_RADIUS_KM = 1.0


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Вычисляет расстояние между двумя точками в км по формуле Haversine."""
    r = 6371.0  # Радиус Земли в км
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def deduplicate_kdtree(df: pd.DataFrame, radius_km: float = DEDUP_RADIUS_KM) -> pd.DataFrame:
    """
    Дедупликация станций с использованием cKDTree для ускорения поиска ближайших соседей.
    Если станции находятся в радиусе radius_km друг от друга — оставляет максимум intensity.
    
    Сложность: O(n log n) вместо O(n²) в наивной реализации.
    """
    if df.empty or len(df) < 2:
        return df

    df = df.reset_index(drop=True)
    
    # Преобразуем координаты в 3D для корректного расчёта расстояний на сфере
    # или используем метрику haversine напрямую через cKDTree с преобразованием
    coords_rad = np.radians(df[["latitude", "longitude"]].values)
    
    # Для малых расстояний можно использовать евклидову метрику с масштабированием
    # 1 градус широты ≈ 111 км, 1 градус долготы ≈ 111 * cos(lat) км
    # Упрощённо используем среднее значение для РФ (~55° с.ш.)
    lat_scale = 111.0
    lon_scale = 111.0 * math.cos(math.radians(55.0))
    
    coords_scaled = df[["latitude", "longitude"]].values.copy()
    coords_scaled[:, 0] *= lat_scale
    coords_scaled[:, 1] *= lon_scale
    
    # Строим KD-дерево
    tree = cKDTree(coords_scaled)
    
    # Находим все пары точек в радиусе radius_km
    pairs = tree.query_pairs(radius_km, output_type='ndarray')
    
    keep = np.ones(len(df), dtype=bool)
    intensities = df["intensity"].values
    
    # Для каждой пары оставляем точку с максимальной интенсивностью
    for i, j in pairs:
        if keep[i] and keep[j]:
            if intensities[j] > intensities[i]:
                keep[i] = False
            else:
                keep[j] = False
    
    result = df[keep].reset_index(drop=True)
    log.info("Дедупликация (cKDTree): %d → %d станций (удалено %d дубликатов)", 
             len(df), len(result), len(df) - len(result))
    
    return result


async def collect_all(wmo_limit: int | None = 200, bbox: tuple | None = None) -> pd.DataFrame:
    """
    Запускает все парсеры параллельно и возвращает единый DataFrame.
    
    Columns: [latitude, longitude, intensity, source, station, timestamp]
    """
    records: list[dict] = []

    limits = httpx.Limits(max_connections=30, max_keepalive_connections=15)
    
    async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:
        # Запускаем все источники параллельно
        metar_task = parsers.fetch_metar(client, RUSSIAN_ICAO_CODES)
        wmo_task = parsers.fetch_wmo_all(client, limit=wmo_limit)
        
        # Дополнительные источники если указан bbox
        openmeteo_task = parsers.fetch_openmeteo_stations(client, bbox) if bbox else asyncio.sleep(0, [])
        rainviewer_task = parsers.fetch_rainviewer_latest_tile_template(client)
        
        results = await __import__("asyncio").gather(
            metar_task, wmo_task, openmeteo_task, rainviewer_task,
            return_exceptions=True
        )

    # Обрабатываем результаты
    for name, res in zip(["METAR", "WMO", "OpenMeteo", "RainViewer"], results):
        if isinstance(res, Exception):
            log.error("Источник %s завершился с ошибкой: %s", name, res)
            continue
        
        if name == "RainViewer":
            # RainViewer возвращает шаблон URL, не точки данных
            if res:
                log.info("RainViewer: шаблон тайлов получен")
            continue
            
        if isinstance(res, list):
            records.extend(res)
            log.info("%s: добавлено %d записей", name, len(res))

    if not records:
        log.warning("Ни один источник не вернул данных.")
        return pd.DataFrame(columns=["latitude", "longitude", "intensity", "source", "station", "timestamp"])

    df = pd.DataFrame.from_records(records)
    
    # Валидация данных
    df = df.dropna(subset=["latitude", "longitude"])
    df["intensity"] = df["intensity"].clip(lower=0.0, upper=5.0)
    
    # Фильтрация по bbox если указан
    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        df = df[
            (df["longitude"] >= min_lon) & (df["longitude"] <= max_lon) &
            (df["latitude"] >= min_lat) & (df["latitude"] <= max_lat)
        ]
        log.info("Отфильтровано по bbox: осталось %d станций", len(df))

    before = len(df)
    df = deduplicate_kdtree(df)
    log.info("Агрегация: %d точек до дедупликации, %d после.", before, len(df))
    
    return df


# Импорты для collect_all (теперь в начале файла)
# httpx и asyncio импортированы выше
