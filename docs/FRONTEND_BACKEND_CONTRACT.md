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

## Customer invitations and links

All routes below use the session and CSRF rules above. Path IDs are positive integers. All timestamps in responses are UTC ISO 8601 strings. Requests have no body unless listed. Successful responses are HTTP 200 unless indicated. Errors are JSON objects with a `detail` field. All routes can return 401 for a missing or expired session, 403 for an incorrect role, origin or CSRF token, and 422 for invalid inputs.

Shopkeeper endpoints derive the store from the session. An absent record or a record belonging to another shop returns 404. In this table, `{base}` means `/api/shopkeeper/customers/{customer_id}`.

| Method and URL | Response and endpoint-specific errors |
| --- | --- |
| `POST /api/customers` | Existing creation endpoint accepts `{"name":"Ramesh","phone_number":"98765-43210"}`. Phone is optional and normalized using registration rules. Existing customer response, 201. |
| `POST {base}/invite` | 201 with `{"invitation_url":"http://localhost:3000/api/customer-invitations/<token>","expires_at":"2026-12-05T12:00:00Z"}`. 409 `INVITATION_PENDING` or `CUSTOMER_ALREADY_LINKED`. |
| `GET {base}/link-status` | `{"linked":false,"linked_at":null,"invitation_status":"PENDING","invitation_expiry":"2026-12-05T12:00:00Z"}`. Status and expiry are null before the first invitation. Status is PENDING, EXPIRED, REVOKED or CLAIMED. |
| `DELETE {base}/invite` | Cancels a pending invitation. Returns the current link-status object. |
| `DELETE {base}/link` | Revokes the active link. Returns the current link-status object. The ledger and receipt history stay with the store. |

Share the invitation URL returned at creation. It uses the first configured application origin (a relative API path if none is configured). It points to authenticated invitation metadata. The frontend can extract the token for its acceptance screen. The raw token is returned once. Revoke a lost pending invitation before issuing a replacement. Expiry is seven days from issuance.

| Method and URL | Customer session required | Success example |
| --- | --- | --- |
| `GET /api/customer-invitations/{token}` | Preview the named store and ledger customer | `{"store_id":2,"store_name":"Kirana","customer_name":"Ramesh","expires_at":"2026-12-05T12:00:00Z"}` |
| `POST /api/customer-invitations/{token}/claim` | Accept the invitation | `{"store_id":2,"store_customer_id":7,"linked_at":"2026-11-28T12:01:00.000Z"}` |

Both routes return 404 for unknown tokens, 410 for expired or revoked tokens, 409 for claimed tokens, and 403 `PHONE_MISMATCH` when a recorded phone differs from the account phone. Claim also returns 409 for a ledger that is already linked or an account already linked in that store. Matching compares normalized numbers. OTP verification is unavailable. A customer may accept a separate invitation from each store.

## Customer stores and notifications

Every route in this section requires a CUSTOMER session. Visibility requires an active link for the authenticated user and the exact store-specific customer record. Revoking a link removes access to that ledger, its receipts and its notifications, including through the older customer routes.

| Method and URL | Success payload |
| --- | --- |
| `GET /api/customer/stores` | Array of store summaries, sorted by store and customer ID. An unlinked account receives `[]`. |
| `GET /api/customer/stores/{store_id}` | One store summary, shown below. |
| `GET /api/customer/stores/{store_id}/ledger?limit=5&cursor=…` | Page of existing ledger history items. Each includes entry and customer IDs, type, amount, balance effect, balance after entry, payment method, batch, correction reference and timestamp. Transcript and language are null. |
| `GET /api/customer/stores/{store_id}/receipts` | Array of issued receipts for the linked ledger, descending entry ID. Uses the existing customer `/api/receipts` representation (entry, customer, shop name, type, amount, balance after, payment method, dates, receipt ID, status, language and nullable dispute). Share token, share URL and reviewer identity are null. Existing receipt rules use decimal strings for paise outside JavaScript's safe integer range. |
| `GET /api/customer/notifications?limit=5&cursor=…` | Page of notification items, example below. |
| `GET /api/customer/notifications/unread-count` | `{"unread_count":2}` across visible stores. |
| `POST /api/customer/notifications/{notification_id}/read` | `{"id":21,"read_at":"2026-11-28T12:05:00.000Z"}`. Repeating preserves the first read time. |
| `POST /api/customer/notifications/read-all` | `{"updated_count":2}` counts newly read items. |

A store-specific route returns 404 for an unlinked store. If an old operator linked multiple ledgers in the same store to one user, store detail routes return 409 `MULTIPLE_LEDGER_RECORDS`. Existing customer-ID routes still expose the individual ledgers. Reading an absent or invisible notification returns 404. Read-all affects only the caller's visible items.

```json
{"store_id":2,"store_name":"Kirana","store_information":{"address":"Pune"},"outstanding_balance_paise":13250,"last_transaction_at":"2026-11-28T12:00:00.000Z","unread_notification_count":1}
```

Address and last transaction can be null. The ledger returns signed integer paise. Pages default to five items and accept limits 1–50. Omit the cursor on the first request and pass back the returned string on subsequent requests. Ledger pages use a snapshot and descending creation time with entry ID as tiebreaker. Notifications use descending creation ID. New notifications do not shift later pages. A malformed cursor returns 422. The final page has a null cursor and `has_more:false`.

```json
{"items":[{"id":21,"store_id":2,"store_name":"Kirana","receipt_id":17,"amount_paise":3250,"created_at":"2026-11-28T12:00:01.000Z","read_at":null,"notification_type":"RECEIPT_AVAILABLE"}],"next_cursor":null,"has_more":false}
```

Generating a receipt creates one notification for the active link at issue time. Sending the receipt or opening an older receipt does not create another notification. A notification insertion error is logged and receipt issuance continues.

## Voice reports

`POST /api/voice/query` requires a SHOPKEEPER session and CSRF header. Send exactly `transcript` (1–2,000 characters), `language` (en-IN, hi-IN or hi-Latn-IN) and `store_id` (integer). For example, send `{"transcript":"Aaj kitne paise aaye?","language":"hi-IN","store_id":2}`.

```json
{"detected_language":"hi-Latn-IN","intent":"COLLECTIONS_QUERY","structured_parameters":{"date":"2026-11-28","timezone":"Asia/Kolkata"},"result":{"amount_paise":3250},"localized_text":"आज ₹32.50 प्राप्त हुए।","speech_text":"आज ₹32.50 प्राप्त हुए।"}
```

`detected_language` describes the transcript. The requested language selects English or Hindi response text (including Hindi speech text for a Hinglish request). The store schema currently has no per-store timezone. Daily reports use the existing India timezone, from local midnight inclusive to the next local midnight exclusive.

| Intent | Structured parameters | Result and accounting basis |
| --- | --- | --- |
| COLLECTIONS_QUERY | date, timezone | `{"amount_paise":3250}`, sum of PAYMENT entries that day |
| CREDIT_QUERY | date, timezone | `{"amount_paise":5000}`, sum of CREDIT entries that day |
| TRANSACTION_COUNT_QUERY | date, timezone | `{"count":3}`, number of ledger entries including adjustments |
| CUSTOMER_BALANCE_QUERY | customer_id | `{"customer_id":7,"customer_name":"Ramesh","balance_paise":13250}`, current signed ledger balance including adjustments |
| TOP_OUTSTANDING_QUERY | empty object | `{"customers":[{"customer_id":7,"customer_name":"Ramesh"}],"balance_paise":13250}`, all customers tied for highest positive balance |

Empty daily reports return zero. An empty outstanding report returns an empty array and zero balance. An unauthorized store returns 404. Unrecognized requests and name clarification return 422 with `{"detail":{"code":"AMBIGUOUS_CUSTOMER","candidates":[{"id":7,"name":"Ramesh"},{"id":8,"name":"Ramesh Sharma"}]}}` or a code such as `MISSING_INTENT` or `CUSTOMER_NOT_FOUND` with an empty array. The report reads the owned store's database in a read-only transaction.

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
