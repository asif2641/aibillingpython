#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt
python scripts/compile_mo.py
BUILD_MODE=True python manage.py collectstatic --no-input
python manage.py migrate --no-input
