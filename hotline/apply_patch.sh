#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="${1:-.}"
echo ">> Using project root: $ROOT_DIR"

echo ">> Copying admin overlay..."
mkdir -p "$ROOT_DIR/hotline/admin/templates"
cp -f overlay/hotline/admin/app.py "$ROOT_DIR/hotline/admin/app.py"
cp -f overlay/hotline/admin/templates/layout.html "$ROOT_DIR/hotline/admin/templates/layout.html"
cp -f overlay/hotline/admin/templates/login.html "$ROOT_DIR/hotline/admin/templates/login.html"
cp -f overlay/hotline/admin/templates/dashboard.html "$ROOT_DIR/hotline/admin/templates/dashboard.html"

echo ">> Patching bot files..."
python3 patches/patch_bot.py "$ROOT_DIR"

echo ">> Done. Rebuild & restart your stack:"
echo "   docker compose build --no-cache bot admin"
echo "   docker compose up -d bot admin"
