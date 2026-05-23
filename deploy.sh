#!/usr/bin/env sh
set -eu

APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
DATA_DIR="${HOMECACHE_DATA_DIR:-$APP_DIR/data}"
BACKUP_DIR="$DATA_DIR/backups"
DATABASE_PATH="$DATA_DIR/inventory.db"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"

cd "$APP_DIR"

mkdir -p "$DATA_DIR" "$BACKUP_DIR"

if [ -f "$DATABASE_PATH" ]; then
    cp "$DATABASE_PATH" "$BACKUP_DIR/inventory-$TIMESTAMP.db"
    echo "Created backup: $BACKUP_DIR/inventory-$TIMESTAMP.db"
fi

if command -v git >/dev/null 2>&1 && [ -d "$APP_DIR/.git" ]; then
    git pull --ff-only
fi

docker compose up -d --build
docker compose ps
