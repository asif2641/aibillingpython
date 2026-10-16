#!/bin/bash
set -e

echo "=== Preparing output directory ==="
mkdir -p staticfiles

echo "=== Setting up build environment ==="
if python3 -m venv .build_venv 2>/dev/null; then
    echo "Using virtual environment .build_venv"
    source .build_venv/bin/activate
    python -m pip install --upgrade pip --quiet
    python -m pip install -r requirements.txt --quiet
    echo "=== Collecting static files ==="
    BUILD_MODE=True python manage.py collectstatic --noinput --clear || true
    deactivate
    rm -rf .build_venv
else
    echo "Using system python with user-site"
    python3 -m pip install --user -r requirements.txt --quiet
    USER_SITE=$(python3 -m site --user-site 2>/dev/null || true)
    if [ -n "$USER_SITE" ]; then
        export PYTHONPATH="$USER_SITE:$PYTHONPATH"
    fi
    echo "=== Collecting static files ==="
    BUILD_MODE=True python3 manage.py collectstatic --noinput --clear || true
fi

echo "=== Mirroring static files for /static/ routing ==="
mkdir -p .static_stage
cp -r staticfiles/* .static_stage/ 2>/dev/null || true
mkdir -p staticfiles/static
cp -r .static_stage/* staticfiles/static/ 2>/dev/null || true
rm -rf .static_stage

echo "=== Build finished successfully ==="
