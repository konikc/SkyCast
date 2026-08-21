"""
SkyCast - Метеорадар осадков на реальных данных.

Веб-сервер с API для получения радарных данных и точечных запросов.
Вдохновлено архитектурой BALTRAD WMS и nowcast.ru/demo.html

API Endpoints:
    GET /                    - Веб-интерфейс карты
    GET /api/radar           - PNG карта текущего состояния
    GET /api/nowcast         - Точечный запрос по координатам
    GET /api/stations        - Список станций в JSON
    GET /api/legend          - Легенда цветовой шкалы
    GET /health              - Health check endpoint
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, PNGResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import httpx

# Добавляем src в path для импортов
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    FEDERAL_DISTRICTS_BBOX,
    WEB_HOST,
    WEB_PORT,
    REQUEST_TIMEOUT,
    CACHE_TTL_SECONDS,
)
from aggregator import collect_all
from interpolation import interpolate_district, interpolate_point_query, get_intensity_description
from visualization import render_to_base64, generate_legend_png

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("skycast.api")

app = FastAPI(
    title="SkyCast Weather Radar API",
    description="API для получения радарных данных об осадках на основе реальных метеостанций",
    version="1.0.0",
)

# CORS для доступа с любого домена (для бесплатного хостинга)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальное состояние для кэширования данных
class RadarCache:
    def __init__(self):
        self.data: Optional[dict] = None
        self.timestamp: Optional[datetime] = None
        self.district_data: dict = {}  # district -> {grid_lon, grid_lat, z, points}
    
    def is_fresh(self, ttl_seconds: int = CACHE_TTL_SECONDS) -> bool:
        if self.timestamp is None:
            return False
        return (datetime.utcnow() - self.timestamp).total_seconds() < ttl_seconds
    
    def invalidate(self):
        self.data = None
        self.timestamp = None

cache = RadarCache()
http_client: Optional[httpx.AsyncClient] = None


@app.on_event("startup")
async def startup():
    global http_client
    log.info("SkyCast API запускается...")
    http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        follow_redirects=True,
    )
    # Создаём директорию для кэша
    Path("data/cache").mkdir(parents=True, exist_ok=True)


@app.on_event("shutdown")
async def shutdown():
    global http_client
    if http_client:
        await http_client.aclose()
    log.info("SkyCast API остановлен")


async def get_radar_data(district: str = "ЦФО") -> dict:
    """Получает свежие данные радара или возвращает закэшированные."""
    
    if cache.is_fresh() and district in cache.district_data:
        log.debug("Используем кэшированные данные для %s", district)
        return cache.district_data[district]
    
    # Собираем свежие данные
    log.info("Сбор данных для округа %s...", district)
    
    try:
        bbox = FEDERAL_DISTRICTS_BBOX.get(district)
        df = await collect_all(wmo_limit=200, bbox=bbox)
        
        if df.empty:
            log.warning("Нет данных от источников")
            return None
        
        result = interpolate_district(df, district)
        
        if result is None:
            log.warning("Интерполяция не удалась для %s", district)
            return None
        
        grid_lon, grid_lat, z = result
        
        # Сохраняем точки станций
        subset = df[
            (df["longitude"] >= bbox[0]) &
            (df["longitude"] <= bbox[2]) &
            (df["latitude"] >= bbox[1]) &
            (df["latitude"] <= bbox[3])
        ]
        points = (subset["longitude"].to_numpy(), subset["latitude"].to_numpy())
        
        # Кэшируем
        cache.district_data[district] = {
            "grid_lon": grid_lon,
            "grid_lat": grid_lat,
            "z": z,
            "points": points,
            "stations_count": len(df),
        }
        cache.timestamp = datetime.utcnow()
        
        log.info("Данные обновлены: %d станций, сетка %dx%d", 
                 len(df), z.shape[0], z.shape[1])
        
        return cache.district_data[district]
        
    except Exception as exc:
        log.error("Ошибка получения данных: %s", exc, exc_info=True)
        return None


@app.get("/", response_class=HTMLResponse)
async def index():
    """Веб-интерфейс карты."""
    html_path = Path(__file__).parent / "templates" / "index.html"
    
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    
    # Fallback минимальный интерфейс
    return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SkyCast - Метеорадар</title>
    <style>
        body { margin: 0; background: #0e1a2b; color: white; font-family: sans-serif; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        h1 { color: #98FB98; }
        #map { width: 100%; height: 600px; background: #1a2a3a; border-radius: 8px; }
        .controls { margin: 20px 0; }
        select, button { padding: 10px 20px; font-size: 16px; margin: 5px; }
        button { background: #228B22; color: white; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #32CD32; }
        #status { margin: 10px 0; padding: 10px; background: #1a2a3a; border-radius: 4px; }
        #radar-image { max-width: 100%; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌤️ SkyCast - Метеорадар Осадков</h1>
        <p>Радар работает на реальных данных метеостанций (METAR, WMO)</p>
        
        <div class="controls">
            <select id="district">
                <option value="ЦФО">Центральный ФО</option>
                <option value="СЗФО">Северо-Западный ФО</option>
                <option value="ЮФО">Южный ФО</option>
                <option value="СКФО">Северо-Кавказский ФО</option>
                <option value="ПФО">Приволжский ФО</option>
                <option value="УФО">Уральский ФО</option>
                <option value="СФО">Сибирский ФО</option>
                <option value="ДФО">Дальневосточный ФО</option>
            </select>
            <button onclick="loadRadar()">Обновить</button>
        </div>
        
        <div id="status">Загрузка...</div>
        <img id="radar-image" alt="Радарная карта" />
    </div>
    
    <script>
        async function loadRadar() {
            const district = document.getElementById('district').value;
            const status = document.getElementById('status');
            const img = document.getElementById('radar-image');
            
            status.textContent = 'Загрузка данных...';
            
            try {
                const response = await fetch('/api/radar?district=' + district);
                const data = await response.json();
                
                if (data.image) {
                    img.src = data.image;
                    status.textContent = 'Станций: ' + data.stations_count + ' | Обновлено: ' + data.timestamp;
                } else {
                    status.textContent = 'Ошибка: ' + (data.error || 'Нет данных');
                }
            } catch (e) {
                status.textContent = 'Ошибка загрузки: ' + e.message;
            }
        }
        
        // Автозагрузка при старте
        loadRadar();
        // Автообновление каждые 5 минут
        setInterval(loadRadar, 300000);
    </script>
</body>
</html>
""")


@app.get("/api/radar")
async def get_radar_image(
    district: str = Query("ЦФО", description="Федеральный округ"),
):
    """Возвращает PNG карту осадков для указанного округа."""
    
    if district not in FEDERAL_DISTRICTS_BBOX:
        raise HTTPException(status_code=400, detail=f"Неизвестный округ: {district}")
    
    data = await get_radar_data(district)
    
    if data is None:
        raise HTTPException(status_code=503, detail="Нет данных для отображения")
    
    image_base64 = render_to_base64(
        data["grid_lon"],
        data["grid_lat"],
        data["z"],
        district,
        data["points"],
    )
    
    return JSONResponse(content={
        "image": image_base64,
        "district": district,
        "stations_count": data["stations_count"],
        "timestamp": cache.timestamp.isoformat() if cache.timestamp else None,
        "grid_shape": [data["z"].shape[0], data["z"].shape[1]],
    })


@app.get("/api/nowcast")
async def get_nowcast(
    lon: float = Query(..., description="Долгота"),
    lat: float = Query(..., description="Широта"),
    district: str = Query("ЦФО", description="Федеральный округ"),
):
    """
    Точечный запрос интенсивности осадков по координатам.
    Аналог эндпоинта nowcast_wsgi из BALTRAD WMS.
    
    Returns:
        intensity: значение 0-5
        description: текстовое описание
        probability: вероятность осадков (0-1)
    """
    
    # Проверяем что координаты в пределах округа
    bbox = FEDERAL_DISTRICTS_BBOX.get(district)
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            log.debug("Координаты вне округа %s, используем ближайший", district)
            # Можно добавить логику выбора ближайшего округа
    
    data = await get_radar_data(district)
    
    if data is None:
        # Пытаемся получить данные без интерполяции
        try:
            df = await collect_all(wmo_limit=200, bbox=None)
            intensity = interpolate_point_query(df, lon, lat, radius_km=150.0)
            
            if intensity is not None:
                desc = get_intensity_description(intensity)
                return JSONResponse(content={
                    "lon": lon,
                    "lat": lat,
                    "intensity": round(intensity, 2),
                    "probability": min(1.0, intensity / 5.0),
                    "description": desc["description"],
                    "level": desc["level"],
                    "color": desc["color"],
                    "source": "stations_interpolation",
                })
        except Exception as exc:
            log.error("Ошибка nowcast: %s", exc)
        
        raise HTTPException(status_code=503, detail="Нет данных для расчёта")
    
    # Интерполяция по сетке
    from scipy.interpolate import RegularGridInterpolator
    
    try:
        interpolator = RegularGridInterpolator(
            (data["grid_lat"][:, 0], data["grid_lon"][0, :]),
            data["z"],
            method='linear',
            bounds_error=False,
            fill_value=0,
        )
        
        intensity = float(interpolator([[lat, lon]])[0])
        intensity = max(0, min(5, intensity))  # clip 0-5
        
        desc = get_intensity_description(intensity)
        
        return JSONResponse(content={
            "lon": lon,
            "lat": lat,
            "intensity": round(intensity, 2),
            "probability": min(1.0, intensity / 5.0),
            "description": desc["description"],
            "level": desc["level"],
            "color": desc["color"],
            "source": "radar_grid",
        })
        
    except Exception as exc:
        log.error("Ошибка интерполяции точки: %s", exc)
        raise HTTPException(status_code=500, detail="Ошибка расчёта")


@app.get("/api/stations")
async def get_stations(
    district: str = Query("ЦФО", description="Федеральный округ"),
):
    """Возвращает список метеостанций в JSON формате."""
    
    if district not in FEDERAL_DISTRICTS_BBOX:
        raise HTTPException(status_code=400, detail=f"Неизвестный округ: {district}")
    
    bbox = FEDERAL_DISTRICTS_BBOX[district]
    
    try:
        df = await collect_all(wmo_limit=200, bbox=bbox)
        
        stations = []
        for _, row in df.iterrows():
            stations.append({
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "intensity": float(row["intensity"]),
                "source": row.get("source", "unknown"),
                "station": row.get("station", "UNKNOWN"),
            })
        
        return JSONResponse(content={
            "district": district,
            "count": len(stations),
            "timestamp": datetime.utcnow().isoformat(),
            "stations": stations,
        })
        
    except Exception as exc:
        log.error("Ошибка получения станций: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/legend")
async def get_legend():
    """Возвращает легенду цветовой шкалы в base64 PNG."""
    legend_base64 = generate_legend_png()
    
    return JSONResponse(content={
        "legend": legend_base64,
        "scale": [
            {"level": 0, "description": "Без осадков", "color": "#000000"},
            {"level": 1, "description": "Слабые осадки", "color": "#98FB98"},
            {"level": 2, "description": "Умеренные осадки", "color": "#228B22"},
            {"level": 3, "description": "Сильные осадки", "color": "#FFD700"},
            {"level": 4, "description": "Очень сильные", "color": "#DC143C"},
            {"level": 5, "description": "Экстремальные/гроза", "color": "#9400D3"},
        ],
    })


@app.get("/health")
async def health_check():
    """Health check endpoint для мониторинга."""
    return JSONResponse(content={
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "cache_fresh": cache.is_fresh(),
        "cache_timestamp": cache.timestamp.isoformat() if cache.timestamp else None,
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT)
