"""
Дополнительные функции для SkyCast:
- Nowcasting (прогноз на 1-2 часа)
- Анимация последовательности радаров
- Экспорт в различные форматы
- Статистика и аналитика
- Уведомления о критических явлениях
"""
from __future__ import annotations

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple, Any
from scipy.ndimage import gaussian_filter
from scipy.interpolate import RegularGridInterpolator

from config import FEDERAL_DISTRICTS_BBOX, RADAR_COLOR_SCALE
from interpolation import interpolate_district, interpolate_point_query

log = logging.getLogger("skycast.advanced")


# =============================================================================
# 1. NOWCASTING - Краткосрочный прогноз осадков (1-2 часа)
# =============================================================================

def calculate_motion_vector(
    grid_lon: np.ndarray,
    grid_lat: np.ndarray,
    z_current: np.ndarray,
    z_previous: Optional[np.ndarray] = None,
    time_delta_minutes: float = 5.0,
) -> Tuple[float, float]:
    """
    Вычисляет вектор движения осадков методом кросс-корреляции.
    
    Args:
        grid_lon, grid_lat: координаты сетки
        z_current: текущее поле интенсивности
        z_previous: предыдущее поле интенсивности (если есть)
        time_delta_minutes: временной интервал в минутах
    
    Returns:
        (vx, vy): скорость движения в км/час по долготе и широте
    """
    if z_previous is None or z_previous.shape != z_current.shape:
        # Если нет предыдущих данных, предполагаем стационарность
        log.debug("Нет предыдущих данных для расчёта вектора движения")
        return (0.0, 0.0)
    
    try:
        # Нормализуем данные
        z_curr_norm = (z_current - z_current.mean()) / (z_current.std() + 1e-6)
        z_prev_norm = (z_previous - z_previous.mean()) / (z_previous.std() + 1e-6)
        
        # Вычисляем кросс-корреляцию для различных сдвигов
        max_shift_x = 10  # пикселей
        max_shift_y = 10
        
        best_corr = -1
        best_shift = (0, 0)
        
        for dx in range(-max_shift_x, max_shift_x + 1, 2):
            for dy in range(-max_shift_y, max_shift_y + 1, 2):
                shifted = np.roll(z_prev_norm, shift=(dy, dx), axis=(0, 1))
                corr = np.corrcoef(z_curr_norm.flatten(), shifted.flatten())[0, 1]
                
                if corr > best_corr:
                    best_corr = corr
                    best_shift = (dx, dy)
        
        # Преобразуем сдвиг в пикселях в скорость км/час
        dx, dy = best_shift
        
        # Размер ячейки сетки в км
        cell_size_km = 0.015 * 111  # ~1.67 км
        
        # Скорость в км/мин
        vx_km_min = (dx * cell_size_km) / time_delta_minutes
        vy_km_min = (dy * cell_size_km) / time_delta_minutes
        
        # В км/час
        vx = vx_km_min * 60
        vy = vy_km_min * 60
        
        log.info("Вектор движения: vx=%.2f км/ч, vy=%.2f км/ч (corr=%.3f)", vx, vy, best_corr)
        return (vx, vy)
        
    except Exception as exc:
        log.error("Ошибка расчёта вектора движения: %s", exc)
        return (0.0, 0.0)


def nowcast_forecast(
    grid_lon: np.ndarray,
    grid_lat: np.ndarray,
    z_current: np.ndarray,
    vx: float = 0.0,
    vy: float = 0.0,
    forecast_minutes: int = 60,
    decay_factor: float = 0.95,
) -> np.ndarray:
    """
    Строит прогноз осадков на заданное время вперёд.
    
    Args:
        grid_lon, grid_lat: координаты сетки
        z_current: текущее поле интенсивности
        vx, vy: скорость движения осадков (км/час)
        forecast_minutes: время прогноза в минутах
        decay_factor: коэффициент затухания интенсивности (0-1)
    
    Returns:
        z_forecast: спрогнозированное поле интенсивности
    """
    try:
        z_forecast = z_current.copy()
        
        # Преобразуем скорость из км/час в градусы/минуту
        # 1 градус широты ≈ 111 км
        # 1 градус долготы ≈ 111 * cos(lat) км
        center_lat = np.mean(grid_lat)
        km_to_deg_lat = 1.0 / 111.0
        km_to_deg_lon = 1.0 / (111.0 * np.cos(np.radians(center_lat)))
        
        # Сдвиг за время прогноза
        shift_lon = vx * forecast_minutes / 60.0 * km_to_deg_lon
        shift_lat = vy * forecast_minutes / 60.0 * km_to_deg_lat
        
        # Создаём сдвинутую сетку
        shifted_lon = grid_lon - shift_lon
        shifted_lat = grid_lat - shift_lat
        
        # Интерполируем на новую сетку
        interpolator = RegularGridInterpolator(
            (grid_lat[:, 0], grid_lon[0, :]),
            z_current,
            method='linear',
            bounds_error=False,
            fill_value=0,
        )
        
        # Создаём точки для интерполяции
        points = np.stack([shifted_lat, shifted_lon], axis=-1)
        z_forecast = interpolator(points)
        
        # Применяем затухание интенсивности со временем
        z_forecast = z_forecast * (decay_factor ** (forecast_minutes / 60.0))
        
        # Ограничиваем диапазон
        z_forecast = np.clip(z_forecast, 0, 5)
        
        log.info("Прогноз на %d минут выполнен", forecast_minutes)
        return z_forecast
        
    except Exception as exc:
        log.error("Ошибка построения прогноза: %s", exc)
        return z_current.copy()


def generate_nowcast_sequence(
    grid_lon: np.ndarray,
    grid_lat: np.ndarray,
    z_current: np.ndarray,
    vx: float = 0.0,
    vy: float = 0.0,
    steps: int = 12,
    step_minutes: int = 5,
) -> List[np.ndarray]:
    """
    Генерирует последовательность кадров прогноза для анимации.
    
    Returns:
        sequence: список массивов [z_t0, z_t1, ..., z_tn]
    """
    sequence = [z_current.copy()]
    
    for i in range(1, steps + 1):
        forecast_time = i * step_minutes
        z_future = nowcast_forecast(
            grid_lon, grid_lat, z_current,
            vx, vy,
            forecast_minutes=forecast_time,
        )
        sequence.append(z_future)
    
    log.info("Сгенерирована последовательность прогноза: %d кадров", len(sequence))
    return sequence


# =============================================================================
# 2. СТАТИСТИКА И АНАЛИТИКА
# =============================================================================

def calculate_precipitation_stats(z: np.ndarray) -> Dict[str, Any]:
    """
    Вычисляет статистику осадков по полю.
    
    Returns:
        dict со статистикой: mean, max, area_*, etc.
    """
    stats = {
        "mean_intensity": float(np.mean(z)),
        "max_intensity": float(np.max(z)),
        "min_intensity": float(np.min(z)),
        "std_intensity": float(np.std(z)),
        "coverage_percent": float(np.sum(z > 0.5) / z.size * 100),
    }
    
    # Площадь зон с различной интенсивностью
    stats["area_light"] = int(np.sum((z >= 0.5) & (z < 1.5)))
    stats["area_moderate"] = int(np.sum((z >= 1.5) & (z < 2.5)))
    stats["area_heavy"] = int(np.sum((z >= 2.5) & (z < 3.5)))
    stats["area_very_heavy"] = int(np.sum((z >= 3.5) & (z < 4.5)))
    stats["area_extreme"] = int(np.sum(z >= 4.5))
    
    return stats


def detect_weather_fronts(
    grid_lon: np.ndarray,
    grid_lat: np.ndarray,
    z: np.ndarray,
    gradient_threshold: float = 0.3,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Обнаруживает атмосферные фронты по градиенту интенсивности осадков.
    
    Args:
        gradient_threshold: порог градиента для обнаружения фронта
    
    Returns:
        (front_lat, front_lon): координаты точек фронта
    """
    try:
        # Вычисляем градиенты
        grad_y, grad_x = np.gradient(z)
        gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
        
        # Находим точки с высоким градиентом
        front_mask = gradient_magnitude > gradient_threshold
        
        front_lat = grid_lat[front_mask]
        front_lon = grid_lon[front_mask]
        
        log.info("Обнаружено %d точек фронта", len(front_lat))
        return (front_lat, front_lon)
        
    except Exception as exc:
        log.error("Ошибка обнаружения фронтов: %s", exc)
        return (np.array([]), np.array([]))


def find_precipitation_cells(
    grid_lon: np.ndarray,
    grid_lat: np.ndarray,
    z: np.ndarray,
    min_intensity: float = 2.0,
    min_area_pixels: int = 10,
) -> List[Dict[str, Any]]:
    """
    Находит отдельные ячейки осадков (convective cells).
    
    Returns:
        список ячеек с параметрами: center, max_intensity, area, bbox
    """
    from scipy.ndimage import label, center_of_mass
    
    # Бинаризуем поле
    binary = (z >= min_intensity).astype(int)
    
    # Маркируем связные области
    labeled, num_features = label(binary)
    
    cells = []
    for i in range(1, num_features + 1):
        mask = (labeled == i)
        
        if np.sum(mask) < min_area_pixels:
            continue
        
        # Находим центр массы
        center_indices = center_of_mass(mask)
        center_lat = float(grid_lat[center_indices])
        center_lon = float(grid_lon[center_indices])
        
        # Максимальная интенсивность в ячейке
        max_int = float(np.max(z[mask]))
        
        # Площадь в км² (приблизительно)
        cell_area_km2 = int(np.sum(mask) * 1.67 * 1.67)  # 1.67 км на пиксель
        
        # Bounding box
        rows, cols = np.where(mask)
        bbox = {
            "min_lat": float(grid_lat[rows.min(), cols.min()]),
            "max_lat": float(grid_lat[rows.max(), cols.max()]),
            "min_lon": float(grid_lon[rows.min(), cols.min()]),
            "max_lon": float(grid_lon[rows.max(), cols.max()]),
        }
        
        cells.append({
            "center": {"lat": center_lat, "lon": center_lon},
            "max_intensity": max_int,
            "area_km2": cell_area_km2,
            "bbox": bbox,
            "pixel_count": int(np.sum(mask)),
        })
    
    log.info("Найдено %d ячеек осадков", len(cells))
    return cells


# =============================================================================
# 3. УВЕДОМЛЕНИЯ О КРИТИЧЕСКИХ ЯВЛЕНИЯХ
# =============================================================================

class WeatherAlert:
    """Класс для генерации предупреждений о опасных явлениях."""
    
    ALERT_LEVELS = {
        0: ("none", "Без предупреждений"),
        1: ("yellow", "Повышенное внимание"),
        2: ("orange", "Опасное явление"),
        3: ("red", "Чрезвычайная ситуация"),
    }
    
    def __init__(self):
        self.alerts: List[Dict[str, Any]] = []
    
    def check_conditions(
        self,
        z: np.ndarray,
        cells: List[Dict[str, Any]],
        district: str,
    ) -> List[Dict[str, Any]]:
        """
        Проверяет условия для генерации предупреждений.
        
        Returns:
            список активных предупреждений
        """
        self.alerts = []
        
        # Проверка на экстремальные осадки
        extreme_pixels = np.sum(z >= 4.5)
        if extreme_pixels > 0:
            level = 3 if extreme_pixels > 50 else 2
            self.alerts.append({
                "type": "extreme_precipitation",
                "level": level,
                "level_name": self.ALERT_LEVELS[level][1],
                "color": self.ALERT_LEVELS[level][0],
                "message": f"Обнаружены зоны экстремальных осадков ({extreme_pixels} зон)",
                "district": district,
                "timestamp": datetime.utcnow().isoformat(),
            })
        
        # Проверка на крупные(convective) ячейки
        large_cells = [c for c in cells if c["area_km2"] > 500 and c["max_intensity"] >= 3.5]
        if large_cells:
            self.alerts.append({
                "type": "convective_storm",
                "level": 2,
                "level_name": "Опасное явление",
                "color": "orange",
                "message": f"Обнаружено {len(large_cells)} крупных грозовых ячеек",
                "cells": large_cells[:5],  # Первые 5
                "district": district,
                "timestamp": datetime.utcnow().isoformat(),
            })
        
        # Проверка на сплошную зону сильных осадков
        heavy_coverage = np.sum(z >= 3.0) / z.size * 100
        if heavy_coverage > 30:
            self.alerts.append({
                "type": "widespread_heavy_rain",
                "level": 2,
                "level_name": "Опасное явление",
                "color": "orange",
                "message": f"Широкая зона сильных осадков ({heavy_coverage:.1f}% территории)",
                "coverage_percent": heavy_coverage,
                "district": district,
                "timestamp": datetime.utcnow().isoformat(),
            })
        
        log.info("Сгенерировано %d предупреждений для %s", len(self.alerts), district)
        return self.alerts
    
    def get_highest_alert(self) -> Optional[Dict[str, Any]]:
        """Возвращает предупреждение наивысшего уровня."""
        if not self.alerts:
            return None
        return max(self.alerts, key=lambda x: x["level"])


# =============================================================================
# 4. ЭКСПОРТ ДАННЫХ
# =============================================================================

def export_to_geojson(
    grid_lon: np.ndarray,
    grid_lat: np.ndarray,
    z: np.ndarray,
    threshold: float = 1.0,
) -> Dict[str, Any]:
    """
    Экспортирует поле осадков в формат GeoJSON.
    
    Args:
        threshold: минимальная интенсивность для включения в экспорт
    
    Returns:
        GeoJSON FeatureCollection
    """
    from scipy.ndimage import label
    
    features = []
    
    # Находим зоны с осадками выше порога
    binary = (z >= threshold).astype(int)
    labeled, num_features = label(binary)
    
    for i in range(1, num_features + 1):
        mask = (labeled == i)
        
        # Получаем координаты границ
        rows, cols = np.where(mask)
        
        if len(rows) == 0:
            continue
        
        # Упрощённо создаём polygon по bounding box
        min_row, max_row = rows.min(), rows.max()
        min_col, max_col = cols.min(), cols.max()
        
        coords = [
            [float(grid_lon[min_row, min_col]), float(grid_lat[min_row, min_col])],
            [float(grid_lon[min_row, max_col]), float(grid_lat[min_row, max_col])],
            [float(grid_lon[max_row, max_col]), float(grid_lat[max_row, max_col])],
            [float(grid_lon[max_row, min_col]), float(grid_lat[max_row, min_col])],
            [float(grid_lon[min_row, min_col]), float(grid_lat[min_row, min_col])],
        ]
        
        max_intensity = float(np.max(z[mask]))
        
        features.append({
            "type": "Feature",
            "properties": {
                "intensity": max_intensity,
                "area_pixels": int(np.sum(mask)),
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [coords],
            },
        })
    
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "timestamp": datetime.utcnow().isoformat(),
            "threshold": threshold,
            "feature_count": len(features),
        },
    }


def export_station_data_csv(
    df: pd.DataFrame,
    output_path: str,
) -> str:
    """
    Экспортирует данные станций в CSV файл.
    
    Args:
        df: DataFrame со станциями
        output_path: путь для сохранения
    
    Returns:
        output_path: путь к сохранённому файлу
    """
    df_export = df.copy()
    df_export["export_timestamp"] = datetime.utcnow().isoformat()
    
    df_export.to_csv(output_path, index=False, encoding="utf-8")
    log.info("Данные станций экспортированы в %s (%d записей)", output_path, len(df_export))
    
    return output_path


# =============================================================================
# 5. СГЛАЖИВАНИЕ И ФИЛЬТРАЦИЯ
# =============================================================================

def smooth_field(
    z: np.ndarray,
    sigma: float = 1.0,
    method: str = "gaussian",
) -> np.ndarray:
    """
    Применяет сглаживание поля осадков.
    
    Args:
        z: поле интенсивности
        sigma: параметр сглаживания
        method: метод сглаживания ("gaussian", "median", "uniform")
    
    Returns:
        z_smooth: сглаженное поле
    """
    from scipy.ndimage import median_filter, uniform_filter
    
    if method == "gaussian":
        z_smooth = gaussian_filter(z, sigma=sigma)
    elif method == "median":
        z_smooth = median_filter(z, size=int(sigma*2)+1)
    elif method == "uniform":
        z_smooth = uniform_filter(z, size=int(sigma*2)+1)
    else:
        log.warning("Неизвестный метод сглаживания: %s, используется gaussian", method)
        z_smooth = gaussian_filter(z, sigma=sigma)
    
    # Сохраняем диапазон 0-5
    z_smooth = np.clip(z_smooth, 0, 5)
    
    return z_smooth


def fill_data_gaps(
    grid_lon: np.ndarray,
    grid_lat: np.ndarray,
    z: np.ndarray,
    max_gap_pixels: int = 5,
) -> np.ndarray:
    """
    Заполняет небольшие пропуски в данных (no-data holes).
    
    Args:
        max_gap_pixels: максимальный размер заполняемых отверстий
    
    Returns:
        z_filled: поле с заполненными пропусками
    """
    from scipy.ndimage import binary_closing, binary_fill_holes
    
    # Находим нулевые значения
    zero_mask = (z == 0)
    
    # Заполняем небольшие отверстия
    filled = binary_fill_holes(zero_mask, structure=np.ones((3, 3)))
    
    # Создаём маску для заполнения
    fill_mask = filled & zero_mask
    
    # Если отверстие слишком большое, не заполняем
    labeled, num_features = label(fill_mask.astype(int))
    for i in range(1, num_features + 1):
        if np.sum(labeled == i) > max_gap_pixels * max_gap_pixels:
            fill_mask[labeled == i] = False
    
    # Интерполируем значения для заполнения
    z_filled = z.copy()
    
    if np.any(fill_mask):
        # Используем соседние значения
        from scipy.interpolate import griddata
        
        valid_points = np.column_stack(np.where(~zero_mask))
        valid_values = z[~zero_mask]
        
        fill_points = np.column_stack(np.where(fill_mask))
        
        if len(valid_points) > 0 and len(fill_points) > 0:
            interpolated = griddata(
                valid_points, valid_values, fill_points,
                method='nearest',
            )
            z_filled[fill_mask] = interpolated
    
    return z_filled


# =============================================================================
# Интеграционные функции
# =============================================================================

def process_radar_with_advanced(
    grid_lon: np.ndarray,
    grid_lat: np.ndarray,
    z: np.ndarray,
    district: str,
    enable_nowcast: bool = True,
    enable_alerts: bool = True,
    smooth_sigma: float = 0.5,
) -> Dict[str, Any]:
    """
    Полный цикл обработки радара с расширенными функциями.
    
    Returns:
        dict с результатами: smoothed_field, nowcast, stats, alerts, cells
    """
    result = {
        "district": district,
        "timestamp": datetime.utcnow().isoformat(),
        "original_shape": z.shape,
    }
    
    # 1. Сглаживание
    z_smooth = smooth_field(z, sigma=smooth_sigma)
    result["smoothed_field"] = z_smooth
    
    # 2. Заполнение пропусков
    z_filled = fill_data_gaps(grid_lon, grid_lat, z_smooth)
    result["filled_field"] = z_filled
    
    # 3. Статистика
    result["statistics"] = calculate_precipitation_stats(z_filled)
    
    # 4. Поиск ячеек
    cells = find_precipitation_cells(grid_lon, grid_lat, z_filled)
    result["cells"] = cells
    
    # 5. Обнаружение фронтов
    fronts = detect_weather_fronts(grid_lon, grid_lat, z_filled)
    result["fronts"] = {
        "lat": fronts[0].tolist() if len(fronts[0]) > 0 else [],
        "lon": fronts[1].tolist() if len(fronts[1]) > 0 else [],
    }
    
    # 6. Прогноз (nowcasting)
    if enable_nowcast:
        vx, vy = calculate_motion_vector(grid_lon, grid_lat, z_filled)
        result["motion_vector"] = {"vx": vx, "vy": vy}
        
        # Генерируем прогноз на 30, 60, 90 минут
        forecasts = {}
        for minutes in [30, 60, 90]:
            z_fc = nowcast_forecast(
                grid_lon, grid_lat, z_filled,
                vx, vy,
                forecast_minutes=minutes,
            )
            forecasts[f"{minutes}min"] = {
                "field": z_fc,
                "stats": calculate_precipitation_stats(z_fc),
            }
        result["forecasts"] = forecasts
    
    # 7. Предупреждения
    if enable_alerts:
        alerter = WeatherAlert()
        alerts = alerter.check_conditions(z_filled, cells, district)
        result["alerts"] = alerts
        result["highest_alert"] = alerter.get_highest_alert()
    
    # 8. GeoJSON экспорт
    geojson = export_to_geojson(grid_lon, grid_lat, z_filled, threshold=1.5)
    result["geojson"] = geojson
    
    log.info("Расширенная обработка завершена для %s", district)
    return result


log.info("Модуль advanced_functions загружен")
