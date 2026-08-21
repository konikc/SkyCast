"""
SkyCast v2 - Модуль работы с основным API radar-wms (github.com/savelov)
Предоставляет WMS-интеграцию для получения радарных карт
"""

import httpx
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from urllib.parse import urlencode, urljoin
import logging

from config import RADAR_WMS_CONFIG, APP_CONFIG

logger = logging.getLogger(__name__)


class RadarWMSClient:
    """Клиент для работы с WMS сервером radar-wms"""
    
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or RADAR_WMS_CONFIG["base_url"]
        self.default_params = RADAR_WMS_CONFIG["wms_params"].copy()
        self._capabilities_cache: Optional[Dict] = None
        self._cache_time: Optional[datetime] = None
        
    async def get_capabilities(self) -> Dict[str, Any]:
        """Получить GetCapabilities документ со списком слоев и временными метками"""
        # Кэширование на 5 минут
        if self._capabilities_cache and self._cache_time:
            age = (datetime.now() - self._cache_time).total_seconds()
            if age < 300:
                return self._capabilities_cache
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = urljoin(self.base_url, RADAR_WMS_CONFIG["capabilities_endpoint"])
                response = await client.get(url)
                response.raise_for_status()
                
                # Парсинг XML Capabilities
                capabilities = self._parse_capabilities(response.text)
                self._capabilities_cache = capabilities
                self._cache_time = datetime.now()
                
                logger.info(f"Получены capabilities от {self.base_url}")
                return capabilities
                
        except Exception as e:
            logger.error(f"Ошибка получения capabilities: {e}")
            return {"layers": [], "error": str(e)}
    
    def _parse_capabilities(self, xml_text: str) -> Dict[str, Any]:
        """Упрощенный парсер WMS Capabilities XML"""
        import xml.etree.ElementTree as ET
        
        try:
            root = ET.fromstring(xml_text)
            ns = {'wms': 'http://www.opengis.net/wms'}
            
            layers = []
            # Ищем все слои
            for layer_elem in root.iter():
                if layer_elem.tag.endswith('Layer'):
                    name_elem = layer_elem.find('.//Name')
                    title_elem = layer_elem.find('.//Title')
                    extent_elem = layer_elem.find('.//Extent[@name="time"]')
                    legend_url_elem = layer_elem.find('.//LegendURL/OnlineResource')
                    
                    if name_elem is not None and name_elem.text:
                        layer_info = {
                            "name": name_elem.text,
                            "title": title_elem.text if title_elem is not None else name_elem.text,
                            "time_values": [],
                            "legend_url": None
                        }
                        
                        # Временные метки
                        if extent_elem is not None and extent_elem.text:
                            layer_info["time_values"] = extent_elem.text.split(',')
                        
                        # URL легенды
                        if legend_url_elem is not None:
                            xlink_href = legend_url_elem.get('{http://www.w3.org/1999/xlink}href')
                            if xlink_href:
                                layer_info["legend_url"] = xlink_href.replace('http://', 'https://')
                        
                        layers.append(layer_info)
            
            return {"layers": layers, "timestamp": datetime.now().isoformat()}
            
        except Exception as e:
            logger.error(f"Ошибка парсинга capabilities: {e}")
            return {"layers": [], "error": str(e)}
    
    async def get_map_image(
        self,
        layer: str,
        bbox: List[float],
        width: int = 800,
        height: int = 600,
        time: Optional[str] = None,
        transparent: bool = True
    ) -> bytes:
        """
        Получить радарное изображение через WMS GetMap
        
        Args:
            layer: имя слоя (radar_composite, nowcast, etc.)
            bbox: [lon_min, lat_min, lon_max, lat_max]
            width: ширина изображения
            height: высота изображения
            time: временная метка (опционально)
            transparent: прозрачность фона
            
        Returns:
            PNG изображение в виде байтов
        """
        params = self.default_params.copy()
        params.update({
            "LAYERS": layer,
            "BBOX": ",".join(map(str, bbox)),
            "WIDTH": str(width),
            "HEIGHT": str(height),
            "TRANSPARENT": "TRUE" if transparent else "FALSE"
        })
        
        if time:
            params["TIME"] = time
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                query_string = urlencode(params)
                url = f"{self.base_url}?{query_string}"
                
                logger.debug(f"WMS запрос: {url}")
                response = await client.get(url)
                response.raise_for_status()
                
                # Проверка Content-Type
                content_type = response.headers.get('Content-Type', '')
                if 'image' not in content_type:
                    logger.warning(f"Неожиданный Content-Type: {content_type}")
                
                return response.content
                
        except Exception as e:
            logger.error(f"Ошибка получения карты: {e}")
            raise
    
    async def get_nowcast_probability(
        self,
        lat: float,
        lon: float,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Получить вероятность осадков из nowcast API
        
        Args:
            lat: широта
            lon: долгота
            start_time: время начала (формат YYYYMMDDHHMM)
            end_time: время окончания
            
        Returns:
            Словарь с временными метками и вероятностями
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                params = {"lat": str(lat), "lon": str(lon)}
                
                if start_time and end_time:
                    params["start"] = start_time
                    params["end"] = end_time
                
                url = urljoin(self.base_url, RADAR_WMS_CONFIG["nowcast_api"])
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                return {"success": True, "data": data, "location": {"lat": lat, "lon": lon}}
                
        except Exception as e:
            logger.error(f"Ошибка получения nowcast: {e}")
            return {"success": False, "error": str(e), "location": {"lat": lat, "lon": lon}}
    
    async def list_available_layers(self) -> List[Dict[str, Any]]:
        """Вернуть список доступных слоев"""
        capabilities = await self.get_capabilities()
        return capabilities.get("layers", [])
    
    async def get_legend_url(self, layer: str) -> Optional[str]:
        """Получить URL легенды для слоя"""
        capabilities = await self.get_capabilities()
        for layer_info in capabilities.get("layers", []):
            if layer_info["name"] == layer:
                return layer_info.get("legend_url")
        return None


# Глобальный клиент (singleton pattern)
_wms_client: Optional[RadarWMSClient] = None


def get_wms_client(base_url: Optional[str] = None) -> RadarWMSClient:
    """Получить или создать WMS клиент"""
    global _wms_client
    if _wms_client is None:
        _wms_client = RadarWMSClient(base_url)
    elif base_url and _wms_client.base_url != base_url:
        _wms_client = RadarWMSClient(base_url)
    return _wms_client


async def test_connection() -> Dict[str, Any]:
    """Тестовое подключение к WMS серверу"""
    client = get_wms_client()
    
    try:
        layers = await client.list_available_layers()
        return {
            "status": "connected",
            "base_url": client.base_url,
            "layers_count": len(layers),
            "layers": [l["name"] for l in layers],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "base_url": client.base_url
        }


if __name__ == "__main__":
    # Тест модуля
    import asyncio
    
    async def main():
        result = await test_connection()
        print(f"Результат теста: {result}")
    
    asyncio.run(main())
