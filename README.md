# BoloHisaab

BoloHisaab is a voice-first digital khata for Indian kirana shops. This foundation includes a responsive dashboard, sample customer balances, a voice entry preview, a dispute list, and a weekly report. The interface uses sample data and the voice preview uses a preset phrase. FastAPI initializes SQLite and exposes a health endpoint. No external API keys are required.

## Run with Docker Compose

Install Docker with the Compose plugin and start the Docker engine. From the repository root, run:

```sh
docker compose up --build
```

Open the [dashboard](http://localhost:3000) or check the [API health endpoint](http://localhost:3000/api/health). The frontend proxies API requests to FastAPI on the internal Compose network. Set `BOLOHISAAB_PORT` before startup to change the host port if 3000 is in use.

A healthy response is HTTP 200 with:

```json
{"status":"ok","database":"connected"}
```

The backend stores SQLite data in the named `sqlite_data` volume. Run `docker compose down` to stop the app and keep the volume.

## Run locally without Docker

Use Python 3.12 and Node.js 22.12 or newer.

In one terminal, from the repository root:

```sh
cd backend
python -m venv .venv
```

Activate the environment with `source .venv/bin/activate` on macOS or Linux, or `.\.venv\Scripts\Activate.ps1` in PowerShell. Then install and run the API:

```sh
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload
```

SQLite is created at `backend/data/bolohisaab.sqlite3` by default. Set `DATABASE_PATH` before starting the backend to use another file.

In another terminal, from the repository root:

```sh
cd frontend
npm ci
npm run dev
```

Open the [Vite development server](http://localhost:5173). Vite proxies `/api` to FastAPI on port 8000.

## Checks

Run from `frontend/`:

```sh
npm run check
npm run build
```

Run from `backend/` with the Python environment active:

```sh
python -m unittest discover -s tests -v
```

Run from the repository root to validate the Compose configuration:

```sh
docker compose config --quiet
```
