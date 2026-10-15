#!/bin/bash
# build_files.sh - Vercel deployment build script
echo "=== Installing dependencies ==="
python3 -m pip install -r requirements.txt

echo "=== Collecting static files ==="
BUILD_MODE=True python3 manage.py collectstatic --noinput --clear

echo "=== Build finished ==="
