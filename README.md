# 🌦️ SkyCast v2.0 — Метеорадар осадков

**Метеорадар реального времени на основе radar-wms (github.com/savelov) с вспомогательными источниками данных**

## 📋 О проекте

SkyCast — это веб-приложение для визуализации радарных данных об осадках в реальном времени. 

### 🔑 Ключевые особенности:

- **Основной источник**: WMS сервер [radar-wms](https://github.com/savelov/radar-wms) (готовые радарные карты)
- **Вспомогательные источники**: METAR (аэропорты), Open-Meteo, WMO/GTS
- **Nowcasting**: Прогноз осадков на 30-120 минут вперёд
- **Бесплатный хостинг**: Поддержка Render, Railway, Fly.io
- **Веб-интерфейс**: Интерактивная карта Leaflet с анимацией

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────────┐
│                    SkyCast Frontend                      │
│              (Leaflet.js + HTML5/CSS3)                   │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP/REST API
┌────────────────────▼────────────────────────────────────┐
│                  FastAPI Server                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │           radar_wms_client.py                     │   │
│  │  • WMS GetMap (радарные изображения)             │   │
│  │  • WMS GetCapabilities (слои, времена)           │   │
│  │  • Nowcast API (вероятность осадков)             │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │         auxiliary_parsers.py                      │   │
│  │  • METAR parser (аэропорты)                      │   │
│  │  • Open-Meteo client (прогноз)                   │   │
│  │  • WMO/GTS client (метеостанции)                 │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 🚀 Быстрый старт

### Локальный запуск

```bash
cd SkyCast_v2/src

# Установка зависимостей
pip install -r requirements.txt

# Запуск сервера
python main.py

# Откройте браузер: http://localhost:8080
```

### Проверка API

```bash
# Статус системы
curl http://localhost:8080/api/status

# Список слоёв
curl http://localhost:8080/api/layers

# Радарное изображение (PNG)
curl -o radar.png "http://localhost:8080/api/radar.png?layer=radar_composite&lon_min=34&lat_min=50&lon_max=42&lat_max=58"

# Nowcast для точки
curl "http://localhost:8080/api/nowcast?lat=55.75&lon=37.61"

# METAR аэропорта
curl http://localhost:8080/api/metar/UUEE
```

---

## 📡 Основной API: radar-wms (savelov)

### WMS Endpoints

**Базовый URL**: `http://localhost:8081` (настраивается в config.py)

#### GetMap (получение карты)
```
GET /?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap
    &LAYERS=radar_composite
    &FORMAT=image/png
    &TRANSPARENT=TRUE
    &CRS=EPSG:4326
    &WIDTH=800&HEIGHT=600
    &BBOX=34.0,50.0,42.0,58.0
```

#### GetCapabilities (мета-данные)
```
GET /?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetCapabilities
```

#### Nowcast (прогноз вероятности)
```
GET /nowcast_wsgi?lat=55.75&lon=37.61
```

### Доступные слои

| Слой | Описание | Единицы |
|------|----------|---------|
| `radar_composite` | Комбинированная карта осадков | мм/ч |
| `radar_dbz` | Отражаемость | dBZ |
| `nowcast` | Прогноз движения осадков | вероятность |
| `precip_accum_1h` | Накопленные осадки за 1 час | мм |

---

## 🔧 Конфигурация

### config.py — основные параметры

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
    "cache_ttl_sec": 300,  # кэш 5 минут
    "default_bbox": [34.0, 50.0, 42.0, 58.0]
}
```

---

## 🌐 Деплой на бесплатный хостинг

### Вариант 1: Render.com

1. Создайте `Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY templates/ ./templates/
EXPOSE 8080
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

2. Push в GitHub
3. Connect repository на render.com
4. Deploy!

### Вариант 2: Railway.app

1. Push в GitHub
2. New Project → Deploy from GitHub
3. Railway автоматически обнаружит Python
4. Готово!

### Вариант 3: Fly.io

```bash
flyctl launch
flyctl deploy
```

---

## 📊 API Reference

### GET /api/radar.png
Получить радарное изображение PNG

**Параметры:**
- `layer` — имя слоя (radar_composite, radar_dbz, nowcast)
- `lon_min`, `lat_min`, `lon_max`, `lat_max` — границы области
- `width`, `height` — размер изображения
- `time` — временная метка (опционально)

### GET /api/layers
Список доступных слоёв с мета-данными

### GET /api/nowcast
Прогноз вероятности осадков

**Параметры:**
- `lat`, `lon` — координаты точки
- `hours` — горизонт прогноза (1-3 часа)

### GET /api/stations
Метеостанции в регионе

**Параметры:**
- `region` — регион (russia_west, central, south)
- `include_metar` — включать ли METAR аэропорты

### GET /api/metar/{icao_code}
METAR данные для аэропорта

### GET /api/forecast
Прогноз погоды из Open-Meteo

### GET /api/status
Статус системы и всех источников данных

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
| 6 | 5.0–7.0 | 🟢 Лайм | Экстремальные |
| 7 | 7.0–10.0 | 🟠 Оранжевый | Штормовые |
| 8 | 10.0–20.0 | 🔴 Красный | Опасные |
| 9 | 20.0–30.0 | 🔴 Тёмно-красный | Критические |
| 10+ | >30.0 | 🟣 Фиолетовый | Катастрофические |

---

## 🛠️ Разработка

### Структура проекта
```
SkyCast_v2/
├── src/
│   ├── config.py              # Конфигурация
│   ├── radar_wms_client.py    # Клиент для WMS API
│   ├── auxiliary_parsers.py   # METAR, Open-Meteo, WMO
│   └── main.py                # FastAPI сервер
├── templates/
│   └── index.html             # Веб-интерфейс
├── requirements.txt
├── Dockerfile
└── README.md
```

### Добавление нового слоя

1. Добавьте слой в `config.py`:
```python
"new_layer": {
    "name": "new_layer",
    "title": "Описание",
    "unit": "единицы",
    "style": "стиль"
}
```

2. Обновите выпадающий список в `index.html`

---

## 📄 Лицензия

Проект использует данные из открытых источников:
- radar-wms: LGPL (github.com/savelov)
- METAR: общественное достояние
- Open-Meteo: бесплатное использование
- WMO/GTS: условия соответствующих агентств

SkyCast код: MIT License

---

## 🤝 Вклад

Pull requests приветствуются! Основные направления развития:
- Поддержка дополнительных WMS серверов
- Улучшение nowcasting алгоритмов
- Мобильное приложение
- Telegram-бот с предупреждениями

---

## 📞 Контакты

- GitHub Issues: для багов и фич
- Email: support@skycast.example.com

**SkyCast v2.0** — Создано с ❤️ для метеонаблюдателей
