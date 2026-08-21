"""
Построение сетки и радиально-базисная интерполяция для SkyCast.
Использует RBF (Radial Basis Function) для эмуляции сплошного радарного поля.
"""
from __future__ import annotations

import logging
import numpy as np
import pandas as pd
from scipy.interpolate import Rbf
from typing import Optional, Tuple

from config import FEDERAL_DISTRICTS_BBOX, GRID_STEP_DEG, RBF_SMOOTH, MIN_STATIONS_FOR_INTERPOLATION

log = logging.getLogger("skycast.interpolation")


def build_grid(bbox: tuple[float, float, float, float], step: float = GRID_STEP_DEG) -> Tuple[np.ndarray, np.ndarray]:
    """
    Строит регулярную сетку для заданного bbox.
    
    Returns:
        grid_lon, grid_lat: meshgrid координат
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    lons = np.arange(min_lon, max_lon, step)
    lats = np.arange(min_lat, max_lat, step)
    grid_lon, grid_lat = np.meshgrid(lons, lats)
    return grid_lon, grid_lat


def interpolate_rbf(
    lon: np.ndarray,
    lat: np.ndarray,
    intensity: np.ndarray,
    grid_lon: np.ndarray,
    grid_lat: np.ndarray,
    smooth: float = RBF_SMOOTH,
) -> np.ndarray:
    """
    Выполняет RBF интерполяцию точек на сетку.
    
    Args:
        lon, lat, intensity: координаты и интенсивность станций
        grid_lon, grid_lat: координаты сетки
        smooth: параметр сглаживания RBF
    
    Returns:
        z: интерполированное поле интенсивности на сетке
    """
    try:
        rbf = Rbf(
            lon,
            lat,
            intensity,
            function="multiquadric",
            smooth=smooth,
        )
        z = rbf(grid_lon, grid_lat)
        z = np.clip(z, 0, 5)
        return z
    except Exception as exc:
        log.error("Ошибка RBF интерполяции: %s", exc)
        raise


def interpolate_district(
    df: pd.DataFrame,
    district: str,
    step: float = GRID_STEP_DEG,
    smooth: float = RBF_SMOOTH,
) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """
    Возвращает (grid_lon, grid_lat, Z) для указанного округа, либо None если данных недостаточно.
    
    Args:
        df: DataFrame со станциями [latitude, longitude, intensity]
        district: название округа из FEDERAL_DISTRICTS_BBOX
        step: шаг сетки в градусах
        smooth: параметр сглаживания RBF
    
    Returns:
        (grid_lon, grid_lat, z) или None
    """
    if district not in FEDERAL_DISTRICTS_BBOX:
        raise ValueError(f"Неизвестный округ: {district}")

    bbox = FEDERAL_DISTRICTS_BBOX[district]
    min_lon, min_lat, max_lon, max_lat = bbox

    # Фильтруем станции внутри bbox (с небольшим запасом)
    margin = step * 5
    subset = df[
        (df["longitude"] >= min_lon - margin) & 
        (df["longitude"] <= max_lon + margin) &
        (df["latitude"] >= min_lat - margin) & 
        (df["latitude"] <= max_lat + margin)
    ]

    if len(subset) < MIN_STATIONS_FOR_INTERPOLATION:
        log.warning(
            "Округ %s: недостаточно точек (%d < %d) для интерполяции.",
            district, len(subset), MIN_STATIONS_FOR_INTERPOLATION
        )
        return None

    grid_lon, grid_lat = build_grid(bbox, step)

    try:
        z = interpolate_rbf(
            subset["longitude"].to_numpy(),
            subset["latitude"].to_numpy(),
            subset["intensity"].to_numpy(),
            grid_lon,
            grid_lat,
            smooth=smooth,
        )
    except Exception as exc:
        log.error("Округ %s: ошибка интерполяции: %s", district, exc)
        return None

    log.info(
        "Округ %s: интерполяция выполнена. Сетка %dx%d, станций: %d",
        district, z.shape[0], z.shape[1], len(subset)
    )
    
    return grid_lon, grid_lat, z


def interpolate_point_query(
    df: pd.DataFrame,
    lon: float,
    lat: float,
    radius_km: float = 100.0,
    smooth: float = RBF_SMOOTH,
) -> Optional[float]:
    """
    Вычисляет интенсивность осадков в конкретной точке по координатам.
    Используется для API эндпоинта /nowcast?lon=...&lat=...
    
    Args:
        df: DataFrame со станциями
        lon, lat: координаты точки запроса
        radius_km: радиус поиска станций для интерполяции
    
    Returns:
        intensity: значение интенсивности 0-5 или None
    """
    # Находим станции в радиусе
    from aggregator import haversine_distance_km
    
    def distance(row):
        return haversine_distance_km(lat, lon, row["latitude"], row["longitude"])
    
    df_with_dist = df.copy()
    df_with_dist["distance"] = df_with_dist.apply(distance, axis=1)
    nearby = df_with_dist[df_with_dist["distance"] <= radius_km]
    
    if len(nearby) < 2:
        log.debug("Точка (%.4f, %.4f): недостаточно близких станций (%d)", lon, lat, len(nearby))
        # Возвращаем среднее по ближайшим если их мало
        if len(nearby) == 1:
            return float(nearby["intensity"].iloc[0])
        return None
    
    # Локальная RBF интерполяция
    try:
        rbf = Rbf(
            nearby["longitude"].values,
            nearby["latitude"].values,
            nearby["intensity"].values,
            function="multiquadric",
            smooth=smooth,
        )
        z = rbf(np.array([lon]), np.array([lat]))
        return float(np.clip(z[0], 0, 5))
    except Exception as exc:
        log.debug("Ошибка интерполяции точки (%.4f, %.4f): %s", lon, lat, exc)
        # Fallback: взвешенное среднее
        weights = 1.0 / (nearby["distance"].values + 1.0)
        return float(np.average(nearby["intensity"].values, weights=weights))


def get_intensity_description(intensity: float) -> dict:
    """
    Возвращает текстовое описание интенсивности осадков.
    
    Returns:
        dict с полями: level, description, color
    """
    if intensity < 0.5:
        return {"level": 0, "description": "Без осадков", "color": "#000000"}
    elif intensity < 1.5:
        return {"level": 1, "description": "Слабые осадки", "color": "#98FB98"}
    elif intensity < 2.5:
        return {"level": 2, "description": "Умеренные осадки", "color": "#228B22"}
    elif intensity < 3.5:
        return {"level": 3, "description": "Сильные осадки", "color": "#FFD700"}
    elif intensity < 4.5:
        return {"level": 4, "description": "Очень сильные осадки", "color": "#DC143C"}
    else:
        return {"level": 5, "description": "Экстремальные осадки/гроза", "color": "#9400D3"}
