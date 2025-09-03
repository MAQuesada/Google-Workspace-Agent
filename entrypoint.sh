#!/bin/sh
set -e


echo "Initializing API..."
exec uvicorn api.core:factory_app --factory --host 0.0.0.0 --port 8000
