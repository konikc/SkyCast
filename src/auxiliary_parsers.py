"""
SkyCast v2 - Вспомогательные парсеры (METAR, Open-Meteo, WMO)
Используются как дополнительные источники данных к основному radar-wms API
"""

import httpx
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import re
import logging

from config import METAR_CONFIG, OPEN_METEO_CONFIG, WMO_CONFIG

logger = logging.getLogger(__name__)


class MetarParser:
    """Парсер METAR данных с аэропортов"""
    
    def __init__(self):
        self.sources = METAR_CONFIG["sources"]
        self.airports = METAR_CONFIG["airports_ru"]
    
    async def get_metar(self, icao_code: str) -> Optional[Dict[str, Any]]:
        """Получить METAR для конкретного аэропорта"""
        for source in self.sources:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    url = f"{source}{icao_code}"
                    response = await client.get(url)
                    
                    if response.status_code == 200:
                        return self._parse_metar(response.text, icao_code)
            except Exception as e:
                logger.debug(f"Ошибка получения METAR от {source}: {e}")
                continue
        
        return None
    
    def _parse_metar(self, raw_text: str, icao_code: str) -> Dict[str, Any]:
        """Распарсить METAR строку"""
        # Упрощенный парсер
        result = {
            "icao": icao_code,
            "raw": raw_text.strip(),
            "timestamp": datetime.now().isoformat(),
            "parsed": {}
        }
        
        # Извлечение температуры
        temp_match = re.search(r'M?(\d{2})/', raw_text)
        if temp_match:
            result["parsed"]["temperature_c"] = int(temp_match.group(1))
        
        # Извлечение видимости
        vis_match = re.search(r'(\d{4})', raw_text)
        if vis_match:
            result["parsed"]["visibility_m"] = int(vis_match.group(1))
        
        # Извлечение ветра
        wind_match = re.search(r'(\d{3})(\d{2})G?(\d{2})?KT', raw_text)
        if wind_match:
            result["parsed"]["wind_direction"] = int(wind_match.group(1))
            result["parsed"]["wind_speed_kt"] = int(wind_match.group(2))
            if wind_match.group(3):
                result["parsed"]["wind_gust_kt"] = int(wind_match.group(3))
        
        # Погодные явления
        weather_phenomena = []
        phenomena_codes = ['RA', 'SN', 'TS', 'BR', 'FG', 'DZ', 'GR', 'GS', 'PL', 'SG']
        for code in phenomena_codes:
            if code in raw_text:
                weather_phenomena.append(code)
        result["parsed"]["weather"] = weather_phenomena
        
        return result
    
    async def get_all_airports(self) -> List[Dict[str, Any]]:
        """Получить METAR со всех настроенных аэропортов"""
        tasks = [self.get_metar(airport) for airport in self.airports]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, dict) and result.get("parsed"):
                valid_results.append(result)
            elif isinstance(result, Exception):
                logger.debug(f"Ошибка для {self.airports[i]}: {result}")
        
        return valid_results


class OpenMeteoClient:
    """Клиент для Open-Meteo API"""
    
    def __init__(self):
        self.base_url = OPEN_METEO_CONFIG["base_url"]
        self.default_params = OPEN_METEO_CONFIG["params"].copy()
    
    async def get_forecast(
        self,
        lat: float,
        lon: float,
        hours: int = 24
    ) -> Dict[str, Any]:
        """Получить прогноз осадков"""
        try:
            params = self.default_params.copy()
            params.update({
                "latitude": str(lat),
                "longitude": str(lon),
                "forecast_days": str(hours // 24 + 1)
            })
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                
                data = response.json()
                return self._process_forecast(data)
                
        except Exception as e:
            logger.error(f"Ошибка Open-Meteo: {e}")
            return {"error": str(e), "location": {"lat": lat, "lon": lon}}
    
    def _process_forecast(self, data: Dict) -> Dict[str, Any]:
        """Обработать данные прогноза"""
        if "hourly" not in data:
            return {"error": "Нет hourly данных"}
        
        hourly = data["hourly"]
        result = {
            "location": {
                "lat": data.get("latitude"),
                "lon": data.get("longitude")
            },
            "timezone": data.get("timezone", "UTC"),
            "forecast": []
        }
        
        times = hourly.get("time", [])
        precip = hourly.get("precipitation", [])
        rain = hourly.get("rain", [])
        showers = hourly.get("showers", [])
        
        for i, time in enumerate(times):
            result["forecast"].append({
                "time": time,
                "precipitation_mm": precip[i] if i < len(precip) else 0,
                "rain_mm": rain[i] if i < len(rain) else 0,
                "showers_mm": showers[i] if i < len(showers) else 0,
                "total_mm": (precip[i] if i < len(precip) else 0) + 
                           (rain[i] if i < len(rain) else 0) + 
                           (showers[i] if i < len(showers) else 0)
            })
        
        return result


class WMOClient:
    """Клиент для WMO/GTS данных"""
    
    def __init__(self):
        self.regions = WMO_CONFIG["regions"]
        # Примечание: реальный доступ к GTS требует специальной авторизации
        # Здесь используется публичный API-агрегатор как пример
    
    async def get_stations_in_region(
        self,
        region: str = "russia_west"
    ) -> List[Dict[str, Any]]:
        """Получить станции в регионе"""
        if region not in self.regions:
            return []
        
        bounds = self.regions[region]
        
        # Используем открытый API для примера
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Пример запроса к открытому источнику
                url = "https://meteorological-observations.p.rapidapi.com/observations"
                params = {
                    "start_lat": str(bounds["lat_min"]),
                    "end_lat": str(bounds["lat_max"]),
                    "start_lon": str(bounds["lon_min"]),
                    "end_lon": str(bounds["lon_max"])
                }
                headers = {
                    "X-RapidAPI-Key": "YOUR_KEY_HERE",  # Требуется ключ
                    "X-RapidAPI-Host": "meteorological-observations.p.rapidapi.com"
                }
                
                # Для демо возвращаем пустой список
                # В продакшене здесь будет реальный запрос
                logger.info(f"Запрос станций в регионе {region}: {bounds}")
                return []
                
        except Exception as e:
            logger.error(f"Ошибка получения WMO данных: {e}")
            return []
    
    async def get_observation(self, station_id: str) -> Optional[Dict[str, Any]]:
        """Получить наблюдения с конкретной станции"""
        # Заглушка для примера
        return {
            "station_id": station_id,
            "timestamp": datetime.now().isoformat(),
            "data": {}
        }


# Синглтоны
_metar_parser: Optional[MetarParser] = None
_openmeteo_client: Optional[OpenMeteoClient] = None
_wmo_client: Optional[WMOClient] = None


def get_metar_parser() -> MetarParser:
    global _metar_parser
    if _metar_parser is None:
        _metar_parser = MetarParser()
    return _metar_parser


def get_openmeteo_client() -> OpenMeteoClient:
    global _openmeteo_client
    if _openmeteo_client is None:
        _openmeteo_client = OpenMeteoClient()
    return _openmeteo_client


def get_wmo_client() -> WMOClient:
    global _wmo_client
    if _wmo_client is None:
        _wmo_client = WMOClient()
    return _wmo_client


async def test_auxiliary_sources() -> Dict[str, Any]:
    """Тест вспомогательных источников"""
    results = {}
    
    # Тест METAR
    metar = get_metar_parser()
    try:
        metar_data = await metar.get_metar("UUEE")
        results["metar"] = {
            "status": "ok" if metar_data else "no_data",
            "sample": metar_data
        }
    except Exception as e:
        results["metar"] = {"status": "error", "error": str(e)}
    
    # Тест Open-Meteo
    om_client = get_openmeteo_client()
    try:
        forecast = await om_client.get_forecast(55.75, 37.61, hours=6)
        results["open_meteo"] = {
            "status": "ok" if "forecast" in forecast else "error",
            "forecast_count": len(forecast.get("forecast", []))
        }
    except Exception as e:
        results["open_meteo"] = {"status": "error", "error": str(e)}
    
    # Тест WMO
    wmo = get_wmo_client()
    results["wmo"] = {
        "status": "configured",
        "regions": list(WMO_CONFIG["regions"].keys())
    }
    
    return results


if __name__ == "__main__":
    async def main():
        results = await test_auxiliary_sources()
        import json
        print(json.dumps(results, indent=2, ensure_ascii=False))
    
    asyncio.run(main())
