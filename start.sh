#!/bin/bash
# Для Render.com: запускаем из папки src
cd /opt/render/project/src/SkyCast_v2/src

# Запуск через uvicorn (рекомендуется для production)
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}