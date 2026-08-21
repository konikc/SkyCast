# SkyCast - Метеорадар Осадков

🌤️ **SkyCast** — система визуализации осадков на основе реальных данных метеостанций (METAR, WMO).  
Вдохновлено архитектурой BALTRAD WMS и демо-страницей nowcast.ru/RAD/demo.html.

## Особенности

- **Реальные данные**: Использует публичные API авиационной метеорологии (METAR) и всемирной сети WMO
- **RBF интерполяция**: Построение сплошного поля осадков по разреженным точкам станций
- **Веб-интерфейс**: Карта с выбором федерального округа и автообновлением
- **REST API**: Эндпоинты для получения карты, точечных запросов (nowcast), списка станций
- **Оптимизация**: cKDTree для быстрой дедупликации станций O(n log n)
- **Бесплатный хостинг**: Может работать на Render, Railway, Fly.io и других бесплатных платформах

# Источники данных

| Источник | URL | Статус | Описание |
|----------|-----|--------|----------|
| METAR | aviationweather.gov | ✅ Работает | Авиационные метеостанции аэродромов |
| WMO/WWIS | worldweather.wmo.int | ✅ Работает | Всемирная сеть метеостанций |
| Open-Meteo | open-meteo.com | ✅ Работает | Бесплатный API без ключа (дополнительно) |
| RainViewer | api.rainviewer.com | ✅ Работает | Радарные тайлы для подложки |

## Новые возможности (v1.1+)

- **Nowcasting**: Краткосрочный прогноз осадков на 30/60/90 минут вперёд
- **Обнаружение ячеек**: Автоматическое выявление convective cells (грозовых ячеек)
- **Предупреждения**: Система алертов об опасных явлениях (жёлтый/оранжевый/красный уровень)
- **Статистика**: Детальная статистика по зонам осадков
- **GeoJSON экспорт**: Экспорт данных в формат GeoJSON для GIS систем
- **Расширенная шкала**: 10-уровневая детализация интенсивности
- **Сглаживание и фильтрация**: Улучшенное качество интерполяции

## Установка

```bash
cd SkyCast
pip install -r requirements.txt
```

## Запуск

### Веб-сервер (API + интерфейс)

```bash
cd src
python main.py
```

Откройте http://localhost:8080 в браузере.

### CLI режим (для тестирования)

```bash
cd src
python -c "
import asyncio
from aggregator import collect_all
from interpolation import interpolate_district

async def test():
    df = await collect_all(wmo_limit=100)
    print(f'Получено {len(df)} станций')
    result = interpolate_district(df, 'ЦФО')
    if result:
        print(f'Интерполяция выполнена: сетка {result[2].shape}')

asyncio.run(test())
"
```

## API Endpoints

| Endpoint | Описание |
|----------|----------|
| `GET /` | Веб-интерфейс карты |
| `GET /api/radar?district=ЦФО` | PNG карта осадков (base64) |
| `GET /api/nowcast?lon=37.6&lat=55.75` | Точечный запрос интенсивности |
| `GET /api/stations?district=ЦФО` | Список станций JSON |
| `GET /api/legend` | Легенда цветовой шкалы |
| `GET /api/advanced?district=ЦФО` | **NEW**: Расширенные данные с nowcasting, ячейками и предупреждениями |
| `GET /health` | Health check |

### Пример ответа /api/advanced

```json
{
  "district": "ЦФО",
  "timestamp": "2024-01-15T12:30:00",
  "stations_count": 156,
  "statistics": {
    "mean_intensity": 1.2,
    "max_intensity": 4.5,
    "coverage_percent": 35.2,
    "area_heavy": 120,
    "area_extreme": 5
  },
  "cells": [
    {
      "center": {"lat": 55.8, "lon": 37.5},
      "max_intensity": 4.2,
      "area_km2": 850,
      "bbox": {...}
    }
  ],
  "alerts": [
    {
      "type": "convective_storm",
      "level": 2,
      "level_name": "Опасное явление",
      "message": "Обнаружено 2 крупных грозовых ячеек"
    }
  ],
  "motion_vector": {"vx": 25.5, "vy": -12.3},
  "forecasts": {
    "30min": {"field": [...], "stats": {...}},
    "60min": {"field": [...], "stats": {...}},
    "90min": {"field": [...], "stats": {...}}
  },
  "geojson": {...}
}
```

### Пример ответа /api/nowcast

```json
{
  "lon": 37.6,
  "lat": 55.75,
  "intensity": 2.5,
  "probability": 0.5,
  "description": "Умеренные осадки",
  "level": 2,
  "color": "#228B22",
  "source": "radar_grid"
}
```

## Шкала интенсивности

| Уровень | Цвет | Описание |
|---------|------|----------|
| 0 | ⬛ Чёрный | Без осадков |
| 1 | 🟩 Светло-зелёный | Слабые осадки |
| 2 | 🟢 Зелёный | Умеренные осадки |
| 3 | 🟡 Жёлтый | Сильные осадки |
| 4 | 🔴 Красный | Очень сильные осадки |
| 5 | 🟣 Фиолетовый | Экстремальные/гроза |

## Развёртывание на бесплатном хостинге

### Render.com

1. Создайте новый Web Service
2. Подключите репозиторий
3. Build Command: `pip install -r SkyCast/requirements.txt`
4. Start Command: `cd SkyCast/src && python main.py`
5. Environment: Python 3

### Railway.app

1. New Project → Deploy from GitHub
2. Выберите репозиторий SkyCast
3. Добавьте переменные окружения (если нужны)
4. Deploy

### Fly.io

```bash
flyctl launch --path ./SkyCast
flyctl deploy
```

## Структура проекта

```
SkyCast/
├── src/
│   ├── config.py          # Конфигурация, bbox округов, шкала
│   ├── parsers.py         # Парсеры источников (METAR, WMO, etc.)
│   ├── aggregator.py      # Сбор данных + cKDTree дедупликация
│   ├── interpolation.py   # RBF интерполяция
│   ├── visualization.py   # Рендер карт, легенды, GeoTIFF
│   └── main.py            # FastAPI веб-сервер
├── static/                # Статические файлы
├── templates/             # HTML шаблоны
├── data/cache/            # Кэш данных
├── requirements.txt       # Зависимости
└── README.md             # Документация
```

## Важные ограничения

⚠️ **Точность данных**: Система строит интерполяцию по наземным станциям, что даёт сглаженную картину.  
Это **не заменяет настоящие метеорадары** с отражаемостью и доплеровской скоростью.

⚠️ **Плотность станций**: В удалённых регионах (Сибирь, Дальний Восток) станций мало, точность ниже.

⚠️ **Частота обновления**: Данные обновляются каждые 5-10 минут в зависимости от доступности источников.

## Лицензия

MIT License — свободное использование с указанием авторства.

## Благодарности

- Архитектурные паттерны заимствованы из [BALTRAD WMS](https://github.com/savelov/radar-wms)
- Демо-интерфейс вдохновлён [nowcast.ru/RAD/demo.html](https://www.nowcast.ru/RAD/demo.html)
- Данные предоставлены aviationweather.gov и worldweather.wmo.int
