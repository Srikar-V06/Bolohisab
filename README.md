# BoloHisaab

BoloHisaab is a voice-first digital khata for Indian kirana shops. It includes a responsive dashboard, sample customer balances, a dispute list, a weekly report, and a Voice Entry page with browser recording and a sample payment. FastAPI initializes SQLite and exposes a health endpoint. No external API keys are required.

## Languages and voice

The app starts in Hindi (hi-IN). Use the header to switch to Indian English (en-IN). Voice Entry has its own speech language selector. The browser stores both preferences independently.

Recording uses your browser’s speech recognition service, which may send audio to the browser provider. The transcript is displayed as returned by the browser. English translations are available for the supplied Hindi sample and supported Hindi payment and credit phrases with numeric amounts. Other recordings can still be read in their original form. Confirmation playback uses the browser’s available voices and keeps the confirmation visible when a suitable voice is unavailable.

To add a language, add the frontend locale catalog and register it in the localization module. Verify script rendering and add a font if needed. Add the locale to the speech choices when you have verified browser support. Update the backend language schema once requests support the new locale. Confirmation and receipt templates interpolate the supplied names, amounts, dates, and IDs as text.

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

## Customers and ledger

The customer API uses the local shop created during database initialization. Send `{"name":"Ramesh"}` to `POST /api/customers` to create a customer. Use `GET /api/customers` to list customers and their balances, `GET /api/customers/{id}` to retrieve one customer, and `GET /api/customers/{id}/ledger` to see entries in posting order.

All ledger amounts and balances are in integer paise. Supply a positive amount for `CREDIT` or `PAYMENT`. A payment lowers the balance. Supply a signed, nonzero amount for an `ADJUSTMENT`. A correction is an adjustment with `corrects_entry_id` pointing to an earlier entry for the same customer. A negative balance represents an overpayment.

Backend callers use `app.ledger.ledger_session(path, write=True)` to create a batch of `LedgerEntryDraft` records with `create_transaction_batch` or a single entry with `create_ledger_entry`. Reuse the same shop and batch ID when retrying. The original batch is returned for identical entries and voice metadata. Reusing an ID with different content raises `BatchConflict`. Use a read session for `calculate_balance` and `get_transaction_history`.

### Seed demo data

Run from the repository root while Compose is up:

```sh
docker compose exec backend python -m app.seed_demo
```

For local development, run `python -m app.seed_demo` from `backend/`. The script adds Ramesh, Suresh, and Sita with sample purchases and cash payments to the local kirana shop. It can be run repeatedly without duplicating the demo. Ramesh’s balance is 125,000 paise (₹1,250) after a ₹1,000 opening credit, a ₹450 purchase, and a ₹200 payment.

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
npm test
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
