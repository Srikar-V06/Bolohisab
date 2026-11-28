# BoloHisaab authentication and authorization

All paths below are relative to the API origin. Serve the UI and API under the same origin where possible. For an explicitly allowed same-site, cross-origin UI, use `credentials: 'include'` on every API request so the browser can receive and send the session cookie. The `SameSite=Lax` cookie requires a same-site UI and API for authenticated fetch calls.

## Registration and sign-in

Send JSON with `Content-Type: application/json`.

| Method and path | JSON fields | Success |
| --- | --- | --- |
| `POST /api/auth/register/shopkeeper` | `full_name`, `phone_number`, `password`, `shop_name`, optional `shop_address` | `201`, account and newly assigned `shop_id` |
| `POST /api/auth/register/customer` | `full_name`, `phone_number`, `password` | `201`, account with `shop_id: null` |
| `POST /api/auth/login` | `phone_number`, `password`, optional `role` | `200`, account and a new session cookie |
| `GET /api/auth/me` | No body | `200`, signed-in account |
| `GET /api/auth/csrf` | No body | `200`, `{"csrf_token":"…"}` |
| `POST /api/auth/logout` | CSRF header, no body required | `204`, session revoked and cookie cleared |

Account responses contain `id`, `full_name`, `normalized_phone_number`, `role`, `shop_id`, `is_active`, `created_at`, and `updated_at`. The only roles are `SHOPKEEPER` and `CUSTOMER`. Registration is followed by login. If the login request specifies a role, the API compares it with the stored role. Use the response role for navigation.

Indian mobile numbers can be supplied in national form or with `+91`. Other international numbers require the country code and leading plus sign. Spaces, hyphens and parentheses are removed before validating and storing a unique normalized number. This is formatting validation. Account registration does not verify possession of a phone number.

Registration accepts passwords of 10–1,024 characters. Send the password exactly as entered, including any leading and trailing spaces. The server stores an [Argon2id hash](https://argon2-cffi.readthedocs.io/en/25.1.0/api.html).

## Session restoration and CSRF

1. At startup or after refreshing, call `GET /api/auth/me`. On `401`, clear the in-memory auth state and show sign-in.
2. After a successful login or restoration, call `GET /api/auth/csrf`. Keep the returned token in memory.
3. Send `X-CSRF-Token: <csrf_token>` for authenticated `POST`, `PUT`, `PATCH`, and `DELETE` requests, including voice parsing and logout. The browser adds its `Origin` header. Browser origins must match the configured allowlist. CLI requests may omit `Origin` but still require the CSRF token for authenticated mutations.
4. On `CSRF_INVALID`, fetch a fresh token. If the session has ended, show sign-in. Ask the user to retry any affected write so the app does not silently replay it.
5. After logout, discard the in-memory CSRF token and account state.

The browser receives a host-only `bolo_session` cookie with `Path=/`, `HttpOnly`, `SameSite=Lax`, and `Secure` in production. The cookie expires after seven days. The server also rejects sessions after 24 hours of inactivity. Successful login rotates the session and its CSRF token in that browser. Do not copy the cookie or CSRF token into localStorage. The database stores the SHA-256 session and CSRF hashes, with a random per-session nonce for reproducing the CSRF token during restoration.

## Store and ledger access

- **Shopkeeper** can list, create, and read their shop’s customer records, read ledger history, run voice parsing and confirmation, and manage that shop’s receipts and disputes. Shop scope comes from the authenticated account. Dispute decisions store the account ID and display name from the session. The legacy `reviewer` input is accepted for compatibility.
- **Customer** can use `GET /api/customers`, `GET /api/customers/{id}`, `GET /api/customers/{id}/ledger`, and `GET /api/receipts`. Those routes return only linked records. Balances remain separate by shop. The receipts list includes generated receipts and omits share tokens and reviewer identities. Customer ledger responses omit original voice transcripts and detected-language metadata because a transcript can contain multiple customers’ information.
- Existing public `/api/receipts/share/{token}` paths continue to support a shared receipt and its response without a session. For browser mutations, configure the receipt-only site as `PUBLIC_RECEIPT_ORIGIN`. Keep the public listener separate from shopkeeper routes.

Registration creates no links to old customer records. An authorized operator independently verifies that the account holder is the intended customer before linking the explicit customer record ID. A customer may have multiple links across different stores. Names are never used to match or merge records.

## Errors

| HTTP status | Example detail | Frontend behavior |
| --- | --- | --- |
| 401 | `INVALID_CREDENTIALS`, `AUTH_REQUIRED` | Show a generic login error or return to sign-in. |
| 403 | `ROLE_FORBIDDEN`, `CSRF_INVALID`, `ORIGIN_NOT_ALLOWED` | Handle session or configuration errors. |
| 404 | `Customer not found`, `ENTRY_NOT_FOUND` | Treat an out-of-scope record like an absent record. |
| 409 | `REGISTRATION_FAILED` | Display a generic registration error. |
| 415 | `JSON_REQUIRED` | Send the auth request as JSON. |
| 422 | `INVALID_AUTH_INPUT` | Check the request fields. The server omits submitted values from validation errors. |
| 429 | `AUTH_RATE_LIMITED` | Wait for the `Retry-After` duration in seconds. |

Login and registration each use a 15-minute window scoped independently by normalized phone and client IP. Login allows 8 per phone and 30 per IP. Registration allows 4 per phone and 15 per IP. Throttles reset at the window boundary.

## Deployment

Local Docker uses `BOLO_ENV=development` and allows the configured shopkeeper port on localhost and 127.0.0.1, plus Vite's 5173 port on those hosts. Set `BOLO_ALLOWED_ORIGINS` to a comma-separated list of exact frontend origins to override the defaults.

For production, set `BOLO_ENV=production` and `BOLO_ALLOWED_ORIGINS=https://your-shop-origin.example`. Use an HTTPS reverse proxy for the shopkeeper app and keep the backend private. The bundled Nginx shopkeeper listener expects a loopback upstream Host header. The HTTPS proxy can set `Host: 127.0.0.1` on its upstream request. Enable `BOLO_AUTH_TRUST_PROXY=1` only when the API is reachable exclusively through a trusted proxy that overwrites `X-Bolo-Client-IP`. The bundled Docker proxy does this. Behind another proxy, configure Nginx to accept the real client IP only from that trusted hop.
