# 📡 SkyCast v2 - Основной API: radar-wms (savelov)

## 🌐 Источник данных

**Репозиторий:** https://github.com/savelov/radar-wms

**Описание:** WMS (Web Map Service) сервер на базе MapServer, предоставляющий радарные карты осадков в реальном времени.

---

## 🔧 Установка radar-wms (для развертывания своего сервера)

### Зависимости (Ubuntu 20.04+)
```bash
sudo apt update
sudo apt install -y libapache2-mod-wsgi-py3 python3-distutils python3-mapscript \
    ttf-mscorefonts-installer python3-netcdf4 python3-rasterio \
    python3-pyproj python3-dateutil h5py pyproj numpy gdal-bin \
    libgdal-dev python3-gdal sqlalchemy
sudo a2enmod wsgi
```

### Конфигурация
1. Скопируйте конфигурационные файлы из репозитория:
   - `baltrad_wms.cfg.template` → `/etc/baltrad_wms.cfg`
   - `baltrad_wms.map` → `/etc/baltrad_wms.map`
   - `baltrad_wsgi.py` → `/var/www/cgi-bin/baltrad_wsgi.py`

2. Отредактируйте `baltrad_wms.cfg`:
   ```ini
   [locations]
   db_uri = sqlite:////var/lib/radar-wms/radar_datasets.db
   baltrad_data_dir = /data/baltrad_files
   wms_data_dir = /var/www/wms_data
   mapfile = /etc/baltrad_wms.map
   online_resource = http://your-domain.com/baltrad_wsgi
   tmpdir = /tmp
   
   [settings]
   enable_countour_maps = false
   
   [logging]
   level = info
   ```

3. Настройте Apache VirtualHost:
   ```apache
   <VirtualHost *:80>
       ServerName your-domain.com
       
       WSGIScriptAlias /baltrad_wsgi /var/www/cgi-bin/baltrad_wsgi.py
       
       <Directory /var/www/cgi-bin>
           Require all granted
       </Directory>
       
       # Nowcast API
       WSGIScriptAlias /nowcast_wsgi /var/www/cgi-bin/nowcast.wsgi
   </VirtualHost>
   ```

### Данные
Радарные данные в формате HDF5 должны быть загружены из сети BALTRAD или других источников.

---

## 📋 WMS API Endpoints

### 1. GetCapabilities
Получение метаданных о доступных слоях и временных метках.

**Запрос:**
```
GET http://localhost:8081/?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetCapabilities
```

**Ответ (XML):**
```xml
<WMS_Capabilities>
  <Service>
    <Name>WMS</Name>
    <Title>BALTRAD WMS Server</Title>
  </Service>
  <Capability>
    <Layer>
      <Name>radar_composite</Name>
      <Title>Композитная карта осадков</Title>
      <Extent name="time">20240821T120000Z,20240821T120500Z,...</Extent>
      <LegendURL>
        <OnlineResource xlink:href="https://.../legend.png"/>
      </LegendURL>
    </Layer>
  </Capability>
</WMS_Capabilities>
```

---

### 2. GetMap
Получение радарного изображения.

**Запрос:**
```
GET http://localhost:8081/?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=radar_composite&FORMAT=image/png&TRANSPARENT=TRUE&CRS=EPSG:4326&BBOX=34.0,50.0,42.0,58.0&WIDTH=800&HEIGHT=600
```

**Параметры:**
| Параметр | Описание | Пример |
|----------|----------|--------|
| SERVICE | Всегда "WMS" | WMS |
| VERSION | Версия WMS | 1.3.0 |
| REQUEST | Тип запроса | GetMap |
| LAYERS | Имя слоя | radar_composite |
| FORMAT | Формат изображения | image/png |
| TRANSPARENT | Прозрачность | TRUE |
| CRS | Система координат | EPSG:4326 |
| BBOX | Границы области | lon_min,lat_min,lon_max,lat_max |
| WIDTH | Ширина (px) | 800 |
| HEIGHT | Высота (px) | 600 |
| TIME | Временная метка (опционально) | 20240821T120000Z |

**Ответ:** PNG изображение (binary)

---

### 3. Nowcast API (REST)
Прогноз вероятности осадков на основе движения радарных полей.

**Запрос:**
```
GET http://localhost:8081/nowcast_wsgi?lon=37.6173&lat=55.7558
```

**Параметры:**
| Параметр | Описание | Обязательный |
|----------|----------|--------------|
| lon | Долгота | Да |
| lat | Широта | Да |
| start | Время начала (YYYYMMDDHHMM) | Нет |
| end | Время окончания (YYYYMMDDHHMM) | Нет |

**Ответ (JSON):**
```json
[
  {"time": "202408211200", "probability": 0},
  {"time": "202408211205", "probability": 15},
  {"time": "202408211210", "probability": 45},
  {"time": "202408211215", "probability": 80},
  {"time": "202408211220", "probability": "nan"}
]
```

---

## 🎨 Доступные слои

### 1. radar_composite
- **Описание:** Композитная карта интенсивности осадков
- **Единицы:** мм/ч
- **Стиль:** Gimet_precip_style
- **Данные:** HDF5 radar files from BALTRAD network

**Шкала интенсивности:**
| Уровень | Диапазон | Интенсивность | Цвет (RGB) |
|---------|----------|---------------|------------|
| 0 | 0-1 | нет осадков | 204,204,204 |
| 1 | 1-78 | 0.10 мм/ч | 155,155,155 |
| 2 | 78-93 | 0.30 мм/ч | 135,135,135 |
| 3 | 93-100 | 0.50 мм/ч | 0,85,255 |
| 4 | 100-110 | 1.00 мм/ч | 0,0,127 |
| 5 | 110-125 | 3.00 мм/ч | 255,255,0 |
| 6 | 125-132 | 5.00 мм/ч | 200,239,4 |
| 7 | 132-137 | 7.00 мм/ч | 255,170,0 |
| 8 | 137-142 | 10.00 мм/ч | 255,85,0 |
| 9 | 142-151 | 20.00 мм/ч | 255,0,0 |
| 10 | 151-157 | 30.00 мм/ч | 128,255,128 |
| 11 | 157-164 | 50.00 мм/ч | 0,170,0 |
| 12 | 164-174 | 100.00 мм/ч | 255,131,245 |
| 13 | 174-255 | >100 мм/ч | 208,0,208 |

---

### 2. radar_dbz
- **Описание:** Радиолокационная отражаемость
- **Единицы:** dBZ
- **Стиль:** Gimet_dbzh_style
- **Данные:** Сырые HDF5 radar files

---

### 3. precip_accum_1h
- **Описание:** Накопленные осадки за 1 час
- **Единицы:** мм
- **Стиль:** Gimet_summ_style
- **Данные:** Calculated from radar composite

---

### 4. phenomena
- **Описание:** Классификация метеоявлений
- **Единицы:** category
- **Стиль:** Gimet_phenomena_style
- **Данные:** Classified radar data

**Категории:**
| Код | Явление |
|-----|---------|
| 0 | нет явлений |
| 1 | обл. сред. яруса |
| 2 | сл. образования |
| 3 | осадки слабые |
| 4 | осадки умеренные |
| 5 | осадки сильные |
| 6 | кучевая обл |
| 7 | ливень слабый |
| 8 | ливень умеренный |
| 9 | ливень сильный |
| 10 | гроза (R) |

---

## 🌍 Альтернативные публичные WMS серверы

| Сервер | URL | Статус | Регион |
|--------|-----|--------|--------|
| radar-south.ru | https://radar-south.ru/cgi-bin/mapserv.fcgi | ⚠️ Может быть недоступен | Юг России |
| baltrad.eu | http://baltrad.eu/wms | ✅ Работает | Европа |

---

## 💻 Использование в SkyCast

### Python клиент
```python
from radar_wms_client import RadarWMSClient

client = RadarWMSClient(base_url="http://localhost:8081")

# Получить изображение радара
image = await client.get_map_image(
    layer="radar_composite",
    bbox=[37.0, 55.0, 38.0, 56.0],
    width=800,
    height=600
)

# Получить вероятность осадков
nowcast = await client.get_nowcast_probability(lat=55.7558, lon=37.6173)
```

### cURL примеры
```bash
# GetMap
curl -o radar.png "http://localhost:8081/?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=radar_composite&FORMAT=image/png&TRANSPARENT=TRUE&CRS=EPSG:4326&BBOX=37.0,55.0,38.0,56.0&WIDTH=800&HEIGHT=600"

# GetCapabilities
curl "http://localhost:8081/?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetCapabilities"

# Nowcast
curl "http://localhost:8081/nowcast_wsgi?lon=37.6173&lat=55.7558"
```

---

## 📝 Лицензия

Репозиторий `radar-wms` распространяется под лицензией LGPL (см. COPYING.LESSER).

---

## 🔗 Ссылки

- GitHub: https://github.com/savelov/radar-wms
- BALTRAD: http://baltrad.eu
- MapServer: https://mapserver.org
- OGC WMS Standard: https://www.ogc.org/standards/wms
