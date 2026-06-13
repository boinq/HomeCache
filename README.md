# HomeCache

HomeCache is a small self-hosted inventory app for food and household items. It tracks products, purchase batches, expiry dates, storage locations, categories, QR labels, and printable inventory summaries.

## Features

- Track items by category, location, storage area, container, brand, and notes
- Add batches/sub-items with quantity, purchase date, expiry date, opened date, and frozen date
- Generate QR codes for batches
- Scan a batch QR code and consume one unit from that batch
- Print labels on A4 sheets or Brother QL-700 62mm paper rolls (`DK-1202`, `DK-2205`, `DK-4205`, `DK-4605`)
- Choose which batches to print and how many copies of each label
- Print an inventory summary list
- Manage categories and locations
- Optional ntfy expiry notifications
- Database backup and restore from the Settings page
- Docker-friendly deployment with persistent SQLite storage

## Run Locally

Create a virtual environment and install dependencies:

```sh
python -m venv .venv
./.venv/Scripts/pip install -r requirements.txt
```

On Linux/macOS, use:

```sh
python -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Start the app:

```sh
uvicorn app.main:app --reload
```

Open:

```text
http://localhost:8000
```

## Docker

Copy the example environment file:

```sh
cp .env.example .env
```

Start HomeCache:

```sh
docker compose up -d --build
```

The database is stored on the host in:

```text
./data/inventory.db
```

## Updating On A Server

For a Docker host or LXC, use the included deploy script:

```sh
chmod +x deploy.sh
./deploy.sh
```

The script creates a timestamped database backup, pulls the latest code, rebuilds the image, and restarts the container.

## Reverse Proxy

If you run HomeCache behind a local reverse proxy, set `BASE_URL` in `.env`:

```sh
BASE_URL=https://homecache.example.local
```

Then restart:

```sh
docker compose up -d
```

## Backups

Backups can be downloaded and restored from the Settings page.

The Docker deploy script also writes pre-update backups to:

```text
./data/backups/
```

## Configuration

Environment variables:

| Name | Default | Description |
| --- | --- | --- |
| `HOMECACHE_PORT` | `8000` | Host port exposed by Docker Compose |
| `HOMECACHE_DATA_DIR` | `./data` | Host directory for persistent app data |
| `BASE_URL` | `http://localhost:8000` | Public URL used for QR codes and links |
| `DATABASE_URL` | `sqlite:////data/inventory.db` in Docker | SQLModel database URL |

## Health Check

HomeCache exposes:

```text
GET /health
```

It returns:

```json
{"status":"ok"}
```
