"""
SkyCast v2 - Главный FastAPI сервер
Основной источник: radar-wms (github.com/savelov)
Вспомогательные: METAR, Open-Meteo, WMO
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import APP_CONFIG, RADAR_WMS_CONFIG, LOGGING_CONFIG
from radar_wms_client import get_wms_client, test_connection as test_wms
from auxiliary_parsers import test_auxiliary_sources, get_metar_parser, get_openmeteo_client

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOGGING_CONFIG["level"]),
    format=LOGGING_CONFIG["format"],
    handlers=[
        logging.FileHandler(LOGGING_CONFIG["file"]),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Глобальное состояние приложения
app_state = {
    "startup_time": None,
    "wms_available": False,
    "last_radar_update": None,
    "cache": {}
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Startup
    logger.info(f"Запуск SkyCast v{APP_CONFIG['version']}")
    app_state["startup_time"] = datetime.now().isoformat()
    
    # Проверка подключения к WMS
    wms_result = await test_wms()
    app_state["wms_available"] = (wms_result.get("status") == "connected")
    logger.info(f"WMS статус: {wms_result}")
    
    yield
    
    # Shutdown
    logger.info("Остановка SkyCast")


app = FastAPI(
    title=APP_CONFIG["name"],
    description=APP_CONFIG["description"],
    version=APP_CONFIG["version"],
    lifespan=lifespan
)

# Шаблоны и статика
templates = Jinja2Templates(directory="templates")


# =============================================================================
# ОСНОВНЫЕ ENDPOINTS
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Веб-интерфейс радара"""
    return templates.TemplateResponse("index.html", {
        "request": {},
        "app_name": APP_CONFIG["name"],
        "version": APP_CONFIG["version"],
        "default_bbox": APP_CONFIG["default_bbox"]
    })


@app.get("/api/radar.png")
async def get_radar_image(
    layer: str = Query("radar_composite", description="Слой радара"),
    lon_min: float = Query(34.0),
    lat_min: float = Query(50.0),
    lon_max: float = Query(42.0),
    lat_max: float = Query(58.0),
    width: int = Query(800),
    height: int = Query(600),
    time: Optional[str] = Query(None)
):
    """
    Получить радарное изображение (PNG)
    
    Основной источник: radar-wms WMS API
    """
    client = get_wms_client()
    
    try:
        bbox = [lon_min, lat_min, lon_max, lat_max]
        image_data = await client.get_map_image(
            layer=layer,
            bbox=bbox,
            width=width,
            height=height,
            time=time
        )
        
        app_state["last_radar_update"] = datetime.now().isoformat()
        
        return Response(
            content=image_data,
            media_type="image/png",
            headers={
                "Cache-Control": f"public, max-age={APP_CONFIG['cache_ttl_sec']}",
                "X-Radar-Layer": layer,
                "X-Radar-Time": app_state["last_radar_update"]
            }
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения радара: {e}")
        raise HTTPException(status_code=503, detail=f"Не удалось получить радар: {str(e)}")


@app.get("/api/layers")
async def list_layers():
    """Список доступных радарных слоев"""
    client = get_wms_client()
    layers = await client.list_available_layers()
    
    return {
        "layers": layers,
        "count": len(layers),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/legend/{layer}")
async def get_legend(layer: str):
    """Получить URL легенды для слоя"""
    client = get_wms_client()
    legend_url = await client.get_legend_url(layer)
    
    if legend_url:
        return {"layer": layer, "legend_url": legend_url}
    else:
        raise HTTPException(status_code=404, detail=f"Легенда для слоя {layer} не найдена")


@app.get("/api/nowcast")
async def get_nowcast(
    lat: float = Query(..., description="Широта"),
    lon: float = Query(..., description="Долгота"),
    hours: int = Query(2, ge=1, le=3)
):
    """
    Прогноз осадков (nowcasting) на основе radar-wms
    
    Возвращает вероятность осадков по времени
    """
    client = get_wms_client()
    result = await client.get_nowcast_probability(lat, lon)
    
    if result.get("success"):
        # Ограничиваем количество часов
        data = result["data"][:hours * 2]  # 2 записи на час
        return {
            "location": {"lat": lat, "lon": lon},
            "forecast": data,
            "generated_at": datetime.now().isoformat(),
            "source": "radar-wms nowcast"
        }
    else:
        raise HTTPException(status_code=503, detail=result.get("error", "Ошибка nowcast"))


@app.get("/api/stations")
async def get_stations(
    region: str = Query("russia_west", description="Регион"),
    include_metar: bool = Query(True)
):
    """
    Список метеостанций в регионе
    
    Вспомогательные источники: METAR, WMO
    """
    from auxiliary_parsers import get_wmo_client
    
    wmo = get_wmo_client()
    stations = await wmo.get_stations_in_region(region)
    
    # Добавляем METAR аэропорты если запрошено
    if include_metar:
        metar_parser = get_metar_parser()
        metar_data = await metar_parser.get_all_airports()
        
        for metar in metar_data:
            stations.append({
                "type": "METAR",
                "id": metar["icao"],
                "data": metar["parsed"],
                "raw": metar["raw"],
                "timestamp": metar["timestamp"]
            })
    
    return {
        "region": region,
        "stations_count": len(stations),
        "stations": stations,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/metar/{icao_code}")
async def get_metar(icao_code: str):
    """METAR данные для конкретного аэропорта"""
    metar_parser = get_metar_parser()
    data = await metar_parser.get_metar(icao_code.upper())
    
    if data:
        return data
    else:
        raise HTTPException(status_code=404, detail=f"METAR для {icao_code} не найден")


@app.get("/api/forecast")
async def get_forecast(
    lat: float = Query(...),
    lon: float = Query(...),
    hours: int = Query(24, ge=1, le=72)
):
    """
    Прогноз погоды из Open-Meteo
    
    Вспомогательный источник
    """
    om_client = get_openmeteo_client()
    forecast = await om_client.get_forecast(lat, lon, hours)
    
    if "error" in forecast:
        raise HTTPException(status_code=503, detail=forecast["error"])
    
    return forecast


@app.get("/api/status")
async def get_status():
    """Статус системы и источников данных"""
    wms_test = await test_wms()
    aux_test = await test_auxiliary_sources()
    
    return {
        "app": {
            "name": APP_CONFIG["name"],
            "version": APP_CONFIG["version"],
            "uptime_since": app_state["startup_time"],
            "last_radar_update": app_state["last_radar_update"]
        },
        "sources": {
            "radar_wms": wms_test,
            "auxiliary": aux_test
        },
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/capabilities")
async def get_capabilities():
    """WMS GetCapabilities документ"""
    client = get_wms_client()
    capabilities = await client.get_capabilities()
    return capabilities


# =============================================================================
# ЗАПУСК
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host=APP_CONFIG["host"],
        port=APP_CONFIG["port"],
        log_level="info"
    )
