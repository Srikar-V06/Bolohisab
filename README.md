# BoloHisaab

BoloHisaab is a voice-first digital khata for Indian kirana shops. Its three screens are Speak, Customers, and Receipts. The app uses the existing FastAPI parser and SQLite ledger. No external API keys are required.

## Languages and voice

The app starts in Hindi (hi-IN). Use the header to switch to Indian English (en-IN). Speak has its own speech language selector, and receipt previews have their own receipt language selector. The browser stores all three preferences independently.

Recording uses your browser’s speech recognition service, which may send audio to the browser provider. Open the app in a browser with Web Speech recognition on localhost or HTTPS. The app shows the original transcript and the parser’s English interpretation when available. Confirm posts the reviewed entries to the ledger. Cancel closes the review. Receipt playback uses the browser’s available voices and keeps the written receipt visible when a suitable voice is unavailable.

To add a language, add the frontend locale catalog and register it in the localization module. Verify script rendering and add a font if needed. Add the locale to the speech choices when you have verified browser support. Update the backend language schema once requests support the new locale. Confirmation and receipt templates interpolate the supplied names, amounts, dates, and IDs as text.

### Local AI for free-form speech (optional)

The built-in rules handle entries in any word order, such as "Ramesh 450 credit" or "रमेश को 450 उधार दिया". For looser speech ("Sunita didi ka 300 wala maal khate mein chadha do"), the backend can ask a small model running on your own machine through [Ollama](https://ollama.com). Nothing leaves the laptop.

```
ollama pull qwen2.5:3b
```

The backend uses `qwen2.5:3b` whenever Ollama is running. The model is consulted only when the rules can't read a sentence, which takes about 3 seconds on a laptop CPU. It only points at words you said. The app converts the amount itself, matches the name against your customers, and asks again if the model names an amount, customer or choice you didn't say. You still review every entry before it's saved. Set `BOLO_LOCAL_MODEL` to another Ollama model to switch models, or set it to an empty value to turn this off. Set `OLLAMA_URL` if Ollama isn't on `http://127.0.0.1:11434`.

### Parse a voice command

Send the exact speech transcript to `POST /api/voice/parse` as `original_transcript`. The request accepts the optional `interface_language` and `speech_language` locale preferences.

```json
{
  "original_transcript": "Ramesh ke khate mein saadhe chaar sau likh do aur usne do sau cash diya hai."
}
```

With Ramesh in the local shop’s customer list, the response is `REVIEW_REQUIRED` with two ordered actions, a 45,000-paise `CREDIT` and a 20,000-paise `PAYMENT` with method `CASH`. It also returns the original transcript, detected language, English interpretation, and localized review message. An explicit account phrase such as “Ramesh ke khate mein … likh do” is a credit command. The parser recognizes Hindi (`hi-IN`), Hinglish (`hi-Latn-IN`), and Indian English (`en-IN`).

If any action is unclear, the response is `CLARIFICATION_REQUIRED` with an empty action list and a localized question. Customer resolution uses the stored names, unique name prefixes, and a small list of explicit cross-script spelling equivalents. A pronoun can refer back to one unambiguous customer in the same command. If more than one customer matches, the response lists the candidate IDs and stored names.

The API reads the shop’s customer names and returns a draft with previous and updated balances. When the shopkeeper selects Confirm, the app sends the reviewed actions, previous balances, original transcript, and a retry-safe batch ID to `POST /api/voice/confirm`. The endpoint rechecks the interpretation and balances before posting the batch. The English interpretation and localized message are display text. The deterministic parser works without API keys. Future adapters can implement `VoiceUnderstandingAdapter` to propose draft actions that still pass the local validation and customer lookup.

## Run with Docker Compose

Install Docker with the Compose plugin and start the Docker engine. From the repository root, run:

```sh
docker compose up --build
```

Open [BoloHisaab](http://localhost:3000) or check the [API health endpoint](http://localhost:3000/api/health). The frontend proxies API requests to FastAPI on the internal Compose network. Set `BOLOHISAAB_PORT` before startup to change the host port if 3000 is in use.

A healthy response is HTTP 200 with:

```json
{"status":"ok","database":"connected"}
```

The backend stores SQLite data in the named `sqlite_data` volume. Run `docker compose down` to stop the app and keep the volume.

## Customers and ledger

The customer API uses the local shop created during database initialization. Send `{"name":"Ramesh"}` to `POST /api/customers` to create a customer. Use `GET /api/customers` to list customers and their balances, `GET /api/customers/{id}` to retrieve one customer, and `GET /api/customers/{id}/ledger` to see entries in posting order.

The Customers screen fetches history five at a time through `GET /api/customers/{id}/ledger?limit=5`. This form returns `items`, `next_cursor`, and `has_more`. Pass the opaque `next_cursor` as the `cursor` query parameter to fetch the next page from the same snapshot. Items are ordered by `created_at DESC, id DESC` and each includes `balance_after_paise`. The original request with no query parameters still returns the full list.

Customer details and receipt previews open as bottom sheets on phones, centred dialogs on tablets, and panels beside their lists on desktop.

All ledger amounts and balances are in integer paise. Supply a positive amount for `CREDIT` or `PAYMENT`. A payment lowers the balance. Supply a signed, nonzero amount for an `ADJUSTMENT`. A correction is an adjustment with `corrects_entry_id` pointing to an earlier entry for the same customer. A negative balance represents an overpayment.

Backend callers use `app.ledger.ledger_session(path, write=True)` to create a batch of `LedgerEntryDraft` records with `create_transaction_batch` or a single entry with `create_ledger_entry`. Reuse the same shop and batch ID when retrying. The original batch is returned for identical entries and voice metadata. Reusing an ID with different content raises `BatchConflict`. Use a read session for `calculate_balance` and `get_transaction_history`.

### Seed demo data

Run from the repository root while Compose is up:

```sh
docker compose exec backend python -m app.seed_demo
```

For local development, run `python -m app.seed_demo` from `backend/`. The script adds Ramesh, Suresh, and Sita with sample purchases and cash payments to the local kirana shop. It can be run repeatedly without duplicating the demo. Ramesh’s balance is 125,000 paise (₹1,250) after a ₹1,000 opening credit, a ₹450 purchase, and a ₹200 payment.

For the Stitch reference data, run `docker compose exec backend python -m app.seed_demo --stitch-preview` against a demo database. The seed creates the four reference customers, ₹4,500 in total outstanding balances, and three receipts ready to prepare.

### Receipts

The Receipts screen lists saved ledger entries. Awaiting includes entries that need a receipt and generated receipts ready to share. Sent shows receipts marked sent after native sharing or after the shopkeeper sends a copied link and selects Mark as sent. A recipient link displays a single receipt in the chosen language. The link must use a deployment the recipient can reach.

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
