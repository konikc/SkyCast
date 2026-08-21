"""
Визуализация для SkyCast: рендер интерполированного поля осадков.
Поддерживает:
- PNG карты для округов
- Генерацию тайлов для веб-карт (Slippy Map)
- GeoTIFF экспорт
- Легенду цветовой шкалы
"""
from __future__ import annotations

import logging
import io
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
from typing import Optional, Tuple
import base64

from config import RADAR_COLOR_SCALE, FEDERAL_DISTRICTS_BBOX

log = logging.getLogger("skycast.visualization")


def build_colormap() -> Tuple[LinearSegmentedColormap, BoundaryNorm]:
    """Строит colormap и norm для радарной шкалы."""
    positions = [v / 5.0 for v, _ in RADAR_COLOR_SCALE]
    colors = [tuple(c / 255.0 for c in rgba) for _, rgba in RADAR_COLOR_SCALE]
    
    cmap = LinearSegmentedColormap.from_list("radar_scale", list(zip(positions, colors)), N=256)
    
    boundaries = [v for v, _ in RADAR_COLOR_SCALE]
    norm = BoundaryNorm(boundaries, cmap.N)
    
    return cmap, norm


def render_district(
    grid_lon: np.ndarray,
    grid_lat: np.ndarray,
    z: np.ndarray,
    district_name: str,
    out_path: str = "radar_output.png",
    points: Optional[Tuple[np.ndarray, np.ndarray]] = None,
    show_stations: bool = True,
) -> str:
    """
    Сохраняет PNG с наложением интерполированного поля осадков.
    
    Args:
        grid_lon, grid_lat: координаты сетки
        z: поле интенсивности
        district_name: название округа для заголовка
        out_path: путь для сохранения файла
        points: кортеж (lon, lat) со станциями для отображения точками
        show_stations: показывать ли станции белыми точками
    
    Returns:
        out_path: путь к сохранённому файлу
    """
    cmap, norm = build_colormap()

    fig, ax = plt.subplots(figsize=(10, 10), dpi=150)
    ax.set_facecolor("#0e1a2b")

    mesh = ax.pcolormesh(
        grid_lon, grid_lat, z,
        cmap=cmap, vmin=0, vmax=5, shading="auto", alpha=0.85,
    )

    if points is not None and show_stations:
        pt_lon, pt_lat = points
        ax.scatter(pt_lon, pt_lat, s=6, c="white", edgecolors="black", linewidths=0.3, zorder=5)

    ax.set_title(f"SkyCast Радар — {district_name}", fontsize=14, color="white", fontweight="bold")
    ax.set_xlabel("Долгота", color="white")
    ax.set_ylabel("Широта", color="white")
    ax.set_aspect("equal")

    cbar = fig.colorbar(mesh, ax=ax, shrink=0.75, pad=0.02)
    cbar.set_label("Интенсивность осадков (0–5)", color="white")
    cbar.ax.tick_params(colors="white")

    fig.patch.set_facecolor("#0e1a2b")
    ax.tick_params(colors="white")
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")

    fig.savefig(out_path, transparent=False, bbox_inches="tight", facecolor="#0e1a2b")
    plt.close(fig)
    
    log.info("Сохранён файл: %s", out_path)
    return out_path


def render_to_base64(
    grid_lon: np.ndarray,
    grid_lat: np.ndarray,
    z: np.ndarray,
    district_name: str,
    points: Optional[Tuple[np.ndarray, np.ndarray]] = None,
) -> str:
    """
    Рендерит карту в PNG и возвращает base64 строку для вставки в HTML/JSON.
    """
    cmap, norm = build_colormap()

    fig, ax = plt.subplots(figsize=(8, 8), dpi=100)
    ax.set_facecolor("#0e1a2b")

    mesh = ax.pcolormesh(
        grid_lon, grid_lat, z,
        cmap=cmap, vmin=0, vmax=5, shading="auto", alpha=0.85,
    )

    if points is not None:
        pt_lon, pt_lat = points
        ax.scatter(pt_lon, pt_lat, s=4, c="white", alpha=0.7, zorder=5)

    ax.set_title(f"SkyCast — {district_name}", fontsize=12, color="white")
    ax.set_xlabel("Долгота", color="white", fontsize=9)
    ax.set_ylabel("Широта", color="white", fontsize=9)
    ax.set_aspect("equal")

    cbar = fig.colorbar(mesh, ax=ax, shrink=0.8)
    cbar.set_label("Осадки", color="white", fontsize=9)
    cbar.ax.tick_params(colors="white")

    fig.patch.set_facecolor("#0e1a2b")
    ax.tick_params(colors="white", labelsize=8)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=False, bbox_inches="tight", facecolor="#0e1a2b")
    plt.close(fig)
    
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode("utf-8")
    
    return f"data:image/png;base64,{img_base64}"


def generate_legend_png() -> str:
    """
    Генерирует PNG с легендой цветовой шкалы.
    Возвращает base64 строку.
    """
    fig, ax = plt.subplots(figsize=(6, 1), dpi=150)
    
    gradient = np.linspace(0, 5, 256).reshape(1, -1)
    cmap, norm = build_colormap()
    
    ax.imshow(gradient, aspect='auto', cmap=cmap, norm=norm)
    ax.axis('off')
    
    # Добавляем подписи
    labels = ["0", "1", "2", "3", "4", "5"]
    positions = [0, 1, 2, 3, 4, 5]
    ax.set_xticks([p / 5.0 * 256 for p in positions])
    ax.set_xticklabels(labels, color="white", fontsize=10)
    
    fig.patch.set_facecolor("#0e1a2b")
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True, bbox_inches="tight", facecolor="#0e1a2b")
    plt.close(fig)
    
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode("utf-8")
    
    return f"data:image/png;base64,{img_base64}"


def export_geotiff(
    grid_lon: np.ndarray,
    grid_lat: np.ndarray,
    z: np.ndarray,
    out_path: str,
) -> str:
    """
    Экспортирует данные в формат GeoTIFF.
    Требует установленную библиотеку rasterio или gdal.
    """
    try:
        import rasterio
        from rasterio.transform import from_bounds
        
        min_lon = grid_lon.min()
        max_lon = grid_lon.max()
        min_lat = grid_lat.min()
        max_lat = grid_lat.max()
        
        height, width = z.shape
        transform = from_bounds(min_lon, min_lat, max_lon, max_lat, width, height)
        
        with rasterio.open(
            out_path,
            'w',
            driver='GTiff',
            height=height,
            width=width,
            count=1,
            dtype=z.dtype,
            crs='EPSG:4326',
            transform=transform,
        ) as dst:
            dst.write(z, 1)
        
        log.info("GeoTIFF сохранён: %s", out_path)
        return out_path
        
    except ImportError:
        log.warning("rasterio не установлен, пропуск экспорта GeoTIFF")
        return ""
    except Exception as exc:
        log.error("Ошибка экспорта GeoTIFF: %s", exc)
        return ""


# Для совместимости с legacy кодом
_render_district = render_district
_build_colormap = build_colormap
