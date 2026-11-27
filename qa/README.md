# BoloHisaab demo QA

Tested the merged UI at 5204085 with the English day-heading correction. The production build passed. Frontend tests passed 13/13 and backend tests passed 38/38, including 74 subtests.

Chromium ran the production frontend against a seeded FastAPI and SQLite instance. The test injected a final speech-recognition transcript for a ₹450 credit to Suresh. Each of the four combinations passed review, confirmation, customer ledger lookup, receipt generation, opening the shared receipt through the copy-link fallback, and marking it sent. The fixture accumulated one credit per run. Physical microphone accuracy, audio playback quality and the native share sheet were outside this run.

| Interface | Width | Speak | Review | Customers | Ledger | Receipt |
|---|---:|---|---|---|---|---|
| hi-IN | 375 | [speak](screenshots/hi-IN-375-speak.png) | [review](screenshots/hi-IN-375-review.png) | [customers](screenshots/hi-IN-375-customers.png) | [ledger](screenshots/hi-IN-375-ledger.png) | [receipt](screenshots/hi-IN-375-receipt.png) |
| hi-IN | 1280 | [speak](screenshots/hi-IN-1280-speak.png) | [review](screenshots/hi-IN-1280-review.png) | [customers](screenshots/hi-IN-1280-customers.png) | [ledger](screenshots/hi-IN-1280-ledger.png) | [receipt](screenshots/hi-IN-1280-receipt.png) |
| en-IN | 375 | [speak](screenshots/en-IN-375-speak.png) | [review](screenshots/en-IN-375-review.png) | [customers](screenshots/en-IN-375-customers.png) | [ledger](screenshots/en-IN-375-ledger.png) | [receipt](screenshots/en-IN-375-receipt.png) |
| en-IN | 1280 | [speak](screenshots/en-IN-1280-speak.png) | [review](screenshots/en-IN-1280-review.png) | [customers](screenshots/en-IN-1280-customers.png) | [ledger](screenshots/en-IN-1280-ledger.png) | [receipt](screenshots/en-IN-1280-receipt.png) |

Keyboard navigation reached the review, save, ledger and receipt controls. The mic and navigation landmark had accessible names in both languages. Reduced-motion styling shortened the page animation to 1 ms. None of the captured views overflowed horizontally. A long Devanagari customer name fit the dialog title in all four configurations.

The contrast ratios of muted text on the page, dues on white, received payments on white, white on primary and amber status text on amber were 5.87, 6.54, 7.22, 7.99 and 6.52 respectively.

**Open keyboard issue (KIR-5, KIR-9).** Focus a customer row, press Enter to open the ledger, then Escape. In every configuration focus fell to the document body. Claude Code owns the shared sheet. Repeat this check after the owner change and verify focus returns to the original row. Cross-review and final sign-off remain open.
