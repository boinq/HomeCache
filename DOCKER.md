# Docker hosting

## First deploy

On your Docker LXC:

```sh
git clone <your-repo-url> HomeCache
cd HomeCache
cp .env.example .env
nano .env
docker compose up -d --build
```

Open:

```text
http://localhost:8000
```

The SQLite database is stored on the host in `./data/inventory.db` and mounted into the container at `/data/inventory.db`.

## Configuration

Edit `.env` on the server:

```sh
HOMECACHE_PORT=8000
HOMECACHE_DATA_DIR=./data
BASE_URL=http://localhost:8000
```

If HomeCache is behind a reverse proxy, set `BASE_URL` to the URL you use in the browser, for example:

```sh
BASE_URL=https://homecache.example.local
```

## Easy updates

The included `deploy.sh` script:

- Creates a timestamped backup of `inventory.db`
- Pulls the latest git changes
- Rebuilds and restarts the container
- Shows container status

Run:

```sh
chmod +x deploy.sh
./deploy.sh
```

Backups are written to:

```text
./data/backups/
```

Useful commands:

```sh
docker compose logs -f
docker compose down
docker compose up -d
```
