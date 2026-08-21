"""
SkyCast v2 - Конфигурация
Основной источник: radar-wms (github.com/savelov)
Вспомогательные: METAR, Open-Meteo, WMO
"""

# =============================================================================
# ОСНОВНОЙ API - RADAR WMS (savelov)
# =============================================================================
# Репозиторий: https://github.com/savelov/radar-wms
# Документация: README, INSTALL, baltrad_wms.cfg.template
# WMS Server: MapServer с поддержкой OGC WMS 1.3.0
# Формат данных: HDF5 с радарными полями осадков (mm/h) и отражаемостью (dBZ)
# =============================================================================
RADAR_WMS_CONFIG = {
    # Базовый URL WMS сервера
    # ВАЖНО: radar-wms требует самостоятельной установки (MapServer + Python + HDF5 данные)
    # Инструкции: см. INSTALL в репозитории savelov/radar-wms
    # Для тестирования можно использовать демо-сервер или поднять локально
    "base_url": "http://localhost:8081",
    
    # Альтернативные публичные WMS серверы (если доступны)
    "alternative_urls": [
        "https://radar-south.ru/cgi-bin/mapserv.fcgi",  # Юг России (может быть недоступен)
        "http://baltrad.eu/wms"  # Европейская сеть BALTRAD
    ],
    
    # Доступные слои (из baltrad_wms.cfg.template)
    # Слои определяются в конфигурации MapServer (baltrad_wms.map)
    "layers": {
        "radar_composite": {
            "name": "radar_composite",
            "title": "Композитная карта осадков",
            "description": "Основные радарные данные об осадках",
            "unit": "mm/h",
            "style": "Gimet_precip_style",
            "data_source": "HDF5 radar files from BALTRAD network"
        },
        "radar_dbz": {
            "name": "radar_dbz", 
            "title": "Отражаемость (dBZ)",
            "description": "Сырые данные радиолокационной отражаемости",
            "unit": "dBZ",
            "style": "Gimet_dbzh_style",
            "data_source": "HDF5 radar files"
        },
        "precip_accum_1h": {
            "name": "precip_accum_1h",
            "title": "Накопленные осадки за 1 час",
            "description": "Суммарное количество осадков за последний час",
            "unit": "mm",
            "style": "Gimet_summ_style",
            "data_source": "Calculated from radar composite"
        },
        "phenomena": {
            "name": "phenomena",
            "title": "Метеоявления",
            "description": "Типы метеорологических явлений (облака, грозы, осадки)",
            "unit": "category",
            "style": "Gimet_phenomena_style",
            "data_source": "Classified radar data"
        }
    },
    
    # Шкалы интенсивности (из Gimet_precip_style в baltrad_wms.cfg.template)
    # SYNTAX: number = name,from,to,R,G,B
    "precip_scale": [
        {"level": 0, "range": [0, 1], "label": "нет осадков", "color": [204, 204, 204]},
        {"level": 1, "range": [1, 78], "label": "0.10 мм/ч", "color": [155, 155, 155]},
        {"level": 2, "range": [78, 93], "label": "0.30 мм/ч", "color": [135, 135, 135]},
        {"level": 3, "range": [93, 100], "label": "0.50 мм/ч", "color": [0, 85, 255]},
        {"level": 4, "range": [100, 110], "label": "1.00 мм/ч", "color": [0, 0, 127]},
        {"level": 5, "range": [110, 125], "label": "3.00 мм/ч", "color": [255, 255, 0]},
        {"level": 6, "range": [125, 132], "label": "5.00 мм/ч", "color": [200, 239, 4]},
        {"level": 7, "range": [132, 137], "label": "7.00 мм/ч", "color": [255, 170, 0]},
        {"level": 8, "range": [137, 142], "label": "10.00 мм/ч", "color": [255, 85, 0]},
        {"level": 9, "range": [142, 151], "label": "20.00 мм/ч", "color": [255, 0, 0]},
        {"level": 10, "range": [151, 157], "label": "30.00 мм/ч", "color": [128, 255, 128]},
        {"level": 11, "range": [157, 164], "label": "50.00 мм/ч", "color": [0, 170, 0]},
        {"level": 12, "range": [164, 174], "label": "100.00 мм/ч", "color": [255, 131, 245]},
        {"level": 13, "range": [174, 255], "label": ">100 мм/ч", "color": [208, 0, 208]}
    ],
    
    # Параметры WMS запроса по умолчанию (OGC WMS 1.3.0)
    "wms_params": {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
        "FORMAT": "image/png",
        "TRANSPARENT": "TRUE",
        "CRS": "EPSG:4326",
        "WIDTH": 800,
        "HEIGHT": 600
    },
    
    # REST API для nowcasting (из nowcast.wsgi в репозитории)
    # Пример: http://localhost/nowcast_wsgi?lon=36.97&lat=55.21
    # Возвращает: 'nan' или вероятность осадков (0-100%)
    "nowcast_api": "/nowcast_wsgi",
    
    # Endpoint для получения GetCapabilities (список слоев и временных меток)
    "capabilities_endpoint": "?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetCapabilities",
    
    # Установка radar-wms (из INSTALL):
    # sudo apt install libapache2-mod-wsgi-py3 python3-distutils python3-mapscript \\
    #     ttf-mscorefonts-installer python3-netcdf4 python3-rasterio python3-pyproj \\
    #     python3-dateutil h5py pyproj numpy gdal
    # sudo a2enmod wsgi
    # Копирование конфигов и настройка Apache
    "installation_notes": {
        "dependencies": [
            "Python 2.6+ or 3.x",
            "MapServer 6+ with Python bindings",
            "SqlAlchemy",
            "h5py", "pyproj", "numpy", "GDAL",
            "Apache with mod_wsgi"
        ],
        "ubuntu_install": [
            "sudo apt install libapache2-mod-wsgi-py3 python3-distutils python3-mapscript",
            "sudo apt install ttf-mscorefonts-installer python3-netcdf4 python3-rasterio",
            "sudo apt install python3-pyproj python3-dateutil h5py pyproj numpy gdal",
            "sudo a2enmod wsgi"
        ],
        "config_files": [
            "baltrad_wms.cfg.template -> /path/to/baltrad_wms.cfg",
            "baltrad_wms.map -> /path/to/baltrad_wms.map",
            "baltrad_wsgi.py -> /var/www/cgi-bin/baltrad_wsgi.py"
        ]
    }
}

# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ API (резервные источники)
# =============================================================================

# METAR данные (аэропорты)
METAR_CONFIG = {
    "enabled": True,
    "sources": [
        "https://metar.vatsim.net/api/metar.php?icao=",
        "https://data.adac.aero/metar/"
    ],
    "airports_ru": [
        "UUEE", "UUDD", "VKOO", "ULLI", "URSS", "URMM", "USPP", "UHWW",
        "UNNT", "UNEE", "USCC", "URRR", "URGS", "UGTB", "UDYZ", "UBBB"
    ],
    "update_interval_sec": 300  # 5 минут
}

# Open-Meteo Radar API
OPEN_METEO_CONFIG = {
    "enabled": True,
    "base_url": "https://api.open-meteo.com/v1/forecast",
    "params": {
        "past_days": 1,
        "forecast_days": 1,
        "hourly": ["precipitation", "rain", "showers"]
    },
    "update_interval_sec": 600  # 10 минут
}

# WMO/GTS данные (всемирная сеть метеостанций)
WMO_CONFIG = {
    "enabled": True,
    "regions": {
        "europe": {"lat_min": 35, "lat_max": 72, "lon_min": -10, "lon_max": 60},
        "russia_west": {"lat_min": 44, "lat_max": 62, "lon_min": 27, "lon_max": 45},
        "russia_central": {"lat_min": 50, "lat_max": 60, "lon_min": 45, "lon_max": 75},
        "russia_south": {"lat_min": 41, "lat_max": 50, "lon_min": 34, "lon_max": 48}
    },
    "update_interval_sec": 900  # 15 минут
}

# =============================================================================
# ШКАЛА ИНТЕНСИВНОСТИ ОСАДКОВ (мм/ч) - из Gimet_precip_style
# =============================================================================
PRECIP_SCALE = [
    {"level": 0, "min": 0, "max": 0.1, "label": "Нет осадков", "color": [204, 204, 204]},
    {"level": 1, "min": 0.1, "max": 0.3, "label": "Слабые", "color": [155, 155, 155]},
    {"level": 2, "min": 0.3, "max": 0.5, "label": "Умеренные", "color": [135, 135, 135]},
    {"level": 3, "min": 0.5, "max": 1.0, "label": "Заметные", "color": [0, 85, 255]},
    {"level": 4, "min": 1.0, "max": 3.0, "label": "Сильные", "color": [0, 0, 127]},
    {"level": 5, "min": 3.0, "max": 5.0, "label": "Очень сильные", "color": [255, 255, 0]},
    {"level": 6, "min": 5.0, "max": 7.0, "label": "Экстремальные", "color": [200, 239, 4]},
    {"level": 7, "min": 7.0, "max": 10.0, "label": "Штормовые", "color": [255, 170, 0]},
    {"level": 8, "min": 10.0, "max": 20.0, "label": "Опасные", "color": [255, 85, 0]},
    {"level": 9, "min": 20.0, "max": 30.0, "label": "Критические", "color": [255, 0, 0]},
    {"level": 10, "min": 30.0, "max": 50.0, "label": "Катастрофические", "color": [128, 255, 128]},
    {"level": 11, "min": 50.0, "max": 100.0, "label": "Чрезвычайные", "color": [0, 170, 0]},
    {"level": 12, "min": 100.0, "max": 999.0, "label": "Рекордные", "color": [255, 131, 245]}
]

# =============================================================================
# НАСТРОЙКИ ПРИЛОЖЕНИЯ
# =============================================================================
APP_CONFIG = {
    "name": "SkyCast",
    "version": "2.0.0",
    "description": "Метеорадар на основе radar-wms (savelov) с вспомогательными источниками",
    
    # Сервер
    "host": "0.0.0.0",
    "port": 8080,
    "debug": False,
    
    # Кэширование
    "cache_ttl_sec": 300,  # 5 минут для радарных данных
    "cache_max_size_mb": 100,
    
    # Область интереса (по умолчанию - Центральная Россия)
    "default_bbox": [34.0, 50.0, 42.0, 58.0],  # [lon_min, lat_min, lon_max, lat_max]
    
    # Частота обновления
    "radar_update_sec": 300,  # 5 минут
    "nowcast_update_sec": 600,  # 10 минут
    
    # Лимиты
    "max_stations": 500,
    "max_forecast_hours": 3
}

# =============================================================================
# НАСТРОЙКИ ДЛЯ БЕСПЛАТНОГО ХОСТИНГА
# =============================================================================
DEPLOY_CONFIG = {
    "render": {
        "plan": "free",
        "memory_mb": 512,
        "disk_gb": 1,
        "notes": "Требуется Dockerfile"
    },
    "railway": {
        "plan": "free",
        "memory_mb": 512,
        "disk_gb": 2,
        "notes": "Автоматический деплой из GitHub"
    },
    "fly_io": {
        "plan": "free",
        "memory_mb": 256,
        "disk_gb": 3,
        "notes": "Требует привязки карты"
    }
}

# =============================================================================
# ЛОГИРОВАНИЕ
# =============================================================================
LOGGING_CONFIG = {
    "level": "INFO",  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": "skycast.log"
}
