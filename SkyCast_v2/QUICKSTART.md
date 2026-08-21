# 🌦️ SkyCast v2.0 — Метеорадар осадков

**Основной API: radar-wms (github.com/savelov)**  
**Вспомогательные источники: METAR, Open-Meteo, WMO**

---

## ✅ Что исправлено в этой версии

### 🔧 Исправления для Render.com:
1. **Dockerfile обновлён** — добавлен `PYTHONPATH=/app/src` и правильный `WORKDIR`
2. **start.sh создан** — скрипт запуска для Render
3. **Импорты работают** — все модули импортируются корректно

### 📡 Основной источник данных:
- **radar-wms WMS API** — готовые радарные карты осадков
- URL по умолчанию: `http://localhost:8081` (настраивается)
- Слои: `radar_composite`, `radar_dbz`, `precip_accum_1h`, `phenomena`

---

## 🚀 Быстрый старт

### Локальный запуск:
```bash
cd SkyCast_v2/src
pip install -r requirements.txt
python main.py
# Откройте http://localhost:8080
```

### На Render.com:

**Build Command:**
```bash
echo "build done"
```

**Start Command:**
```bash
cd SkyCast_v2/src && uvicorn main:app --host 0.0.0.0 --port $PORT
```

Или используйте Dockerfile (уже включён).

---

## 📡 RADAR-WMS API (Основной)

### Репозиторий:
https://github.com/savelov/radar-wms

### WMS Endpoints:

#### GetMap (получение карты):
```
GET /?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap
    &LAYERS=radar_composite
    &FORMAT=image/png
    &TRANSPARENT=TRUE
    &CRS=EPSG:4326
    &WIDTH=800&HEIGHT=600
    &BBOX=34.0,50.0,42.0,58.0
```

#### GetCapabilities (мета-данные):
```
GET /?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetCapabilities
```

#### Nowcast (прогноз вероятности):
```
GET /nowcast_wsgi?lat=55.75&lon=37.61
```

### Доступные слои:

| Слой | Описание | Единицы |
|------|----------|---------|
| `radar_composite` | Комбинированная карта осадков | мм/ч |
| `radar_dbz` | Отражаемость | dBZ |
| `precip_accum_1h` | Накопленные осадки за 1 час | мм |
| `phenomena` | Метеоявления | category |

---

## 🌐 API Endpoints SkyCast

| Endpoint | Описание | Статус |
|----------|----------|--------|
| `GET /` | Веб-интерфейс | ✅ Работает |
| `GET /api/status` | Статус системы | ✅ Работает |
| `GET /api/layers` | Список слоёв | ✅ Работает |
| `GET /api/capabilities` | WMS Capabilities | ✅ Работает |
| `GET /api/radar.png` | PNG изображение радара | ⚠️ Требует WMS сервер |
| `GET /api/nowcast` | Прогноз осадков | ⚠️ Требует WMS сервер |
| `GET /api/legend/{layer}` | Легенда слоя | ⚠️ Требует WMS сервер |
| `GET /api/stations` | Метеостанции | ✅ Работает |
| `GET /api/metar/{icao}` | METAR аэропорта | ⚠️ Требует API ключ |
| `GET /api/forecast` | Прогноз Open-Meteo | ✅ Работает |

---

## 📦 Структура проекта

```
SkyCast_v2/
├── src/
│   ├── config.py              # Конфигурация (RADAR_WMS_CONFIG)
│   ├── radar_wms_client.py    # Клиент для WMS API (основной)
│   ├── auxiliary_parsers.py   # METAR, Open-Meteo, WMO (вспомогательные)
│   └── main.py                # FastAPI сервер (11 endpoints)
├── templates/
│   └── index.html             # Веб-интерфейс (Leaflet.js)
├── Dockerfile                 # Для деплоя
├── requirements.txt           # Зависимости
├── start.sh                   # Скрипт запуска для Render
└── README.md                  # Документация
```

---

## 🔧 Конфигурация

### config.py — основные параметры:

```python
RADAR_WMS_CONFIG = {
    "base_url": "http://localhost:8081",  # URL вашего WMS сервера
    "layers": {...},
    "wms_params": {...},
    "nowcast_api": "/nowcast_wsgi"
}

APP_CONFIG = {
    "host": "0.0.0.0",
    "port": 8080,
    "cache_ttl_sec": 300,
    "default_bbox": [34.0, 50.0, 42.0, 58.0]
}
```

---

## 🌐 Деплой на бесплатный хостинг

### Render.com:
1. Push в GitHub
2. Connect repository на render.com
3. Build Command: `echo "build done"`
4. Start Command: `cd SkyCast_v2/src && uvicorn main:app --host 0.0.0.0 --port $PORT`

### Railway.app:
1. Push в GitHub
2. New Project → Deploy from GitHub
3. Автоматически обнаружит Python

### Fly.io:
```bash
flyctl launch
flyctl deploy
```

---

## 📊 Тесты API

Все endpoints протестированы:
- ✅ HTML интерфейс работает
- ✅ System Status возвращает полную информацию
- ✅ Layers List доступен (пустой без WMS сервера)
- ✅ WMS Capabilities endpoint работает
- ✅ Stations API возвращает данные региона
- ✅ Forecast API (Open-Meteo) полностью рабочий
- ⚠️ Radar PNG требует запущенный WMS сервер
- ⚠️ METAR требует действительный API ключ

---

## 🎨 Шкала интенсивности осадков

| Уровень | Интенсивность (мм/ч) | Цвет | Описание |
|---------|---------------------|------|----------|
| 0 | 0–0.1 | ⚪ Серый | Нет осадков |
| 1 | 0.1–0.3 | ◻️ Светло-серый | Слабые |
| 2 | 0.3–0.5 | ◻️ Серый | Умеренные |
| 3 | 0.5–1.0 | 🔵 Синий | Заметные |
| 4 | 1.0–3.0 | 🔷 Тёмно-синий | Сильные |
| 5 | 3.0–5.0 | 🟡 Жёлтый | Очень сильные |
| 6+ | >5.0 | 🟠🔴🟣 | Экстремальные/Опасные |

---

## 🛠️ Установка radar-wms (локально)

Для полноценной работы радара нужно поднять WMS сервер:

```bash
# Ubuntu/Debian
sudo apt install libapache2-mod-wsgi-py3 python3-distutils python3-mapscript
sudo apt install ttf-mscorefonts-installer python3-netcdf4 python3-rasterio
sudo apt install python3-pyproj python3-dateutil h5py pyproj numpy gdal
sudo a2enmod wsgi

# Клонирование radar-wms
git clone https://github.com/savelov/radar-wms.git
cd radar-wms

# Настройка конфигов (см. INSTALL в репозитории)
# Запуск Apache с WMS модулем
```

---

## 📄 Лицензия

- radar-wms: LGPL (github.com/savelov)
- METAR: общественное достояние
- Open-Meteo: бесплатное использование
- SkyCast код: MIT License

---

## 🤝 Вклад

Pull requests приветствуются!

**SkyCast v2.0** — Создано с ❤️ для метеонаблюдателей
