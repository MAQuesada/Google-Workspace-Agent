#!/bin/sh
set -e  # the script will stop if there are errors

echo "Initializing API..."
exec uvicorn api.core:factory_app --factory --host 0.0.0.0 --port 8000 --reload
