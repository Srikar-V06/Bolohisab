# BoloHisaab design rules

BoloHisaab is the khata book a kirana shopkeeper keeps behind the counter, turned into something they talk to. The UI should feel like a well-kept ledger: calm, legible at arm's length, and trustworthy with money. Personality comes from the type and the voice moment, not from decoration.

All tokens live in `src/styles.css` (`@theme` and `:root`). Use them; don't hard-code new colours, sizes or durations.

## Colour
The interface is mostly neutral. Green is the only brand accent; red and green on amounts carry meaning, not decoration.

| Token | Hex | Use |
|---|---|---|
| `--color-surface` | `#F4F6F3` | Page background |
| `--color-card` | `#FFFFFF` | Raised surfaces: lists, sheets, nav |
| `--color-ink` | `#15211A` | Text |
| `--color-muted` | `#56625A` | Secondary text (≥4.5:1 on surface) |
| `--color-line` | `#DDE4DE` | Hairlines and borders |
| `--color-primary` | `#0F5C41` | Primary button, active nav, focus ring. The only filled accent. |
| `--dues` | `#B3261E` | Money the customer owes (credit given) |
| `--green` | `#146348` | Money received (payment) |
| `--mint` / `--amber` | `#E3F1E9` / `#FCEFC7` | Soft status backgrounds only |

- One filled (primary) button per view. Everything else is the secondary or plain style.
- Never violet, never gradients.

## Type
- **Baloo 2** (`font-display`) is for the brand, page titles and money amounts. It has matching Devanagari and Latin, so Hindi and English headings feel the same.
- **Inter + Noto Sans Devanagari** (`font-sans`) is for everything else.
- Scale: 13 (label) · 14 (small) · 16 (body) · 18 (lead) · 22 (title) · 28 (page) · 36 (hero amount). `text-xs` is 13px; nothing is smaller.
- Amounts use `tabular-nums` and right alignment in lists.
- Labels are sentence case. No all-caps, no letter-spaced eyebrows.

## Layout
- Phone first (375px). 16px side gutter, 44px minimum tap target.
- At ≥1024px the bottom bar becomes a left sidebar and the content column widens to `--content-width`. Screens can use the extra room for a side-by-side detail view.
- Group related rows in one bordered list with hairline dividers instead of a separate card per row. Cards are for a summary or a single object.
- Radius: 8 (small controls), 12 (inputs, rows), 20 (cards, sheets), full (pills, chips, avatars).
- Shadow `--shadow-float` only on things that float: the nav bar and sheets.

## Motion
Motion answers what the user did; nothing animates on its own except the live mic.

| Token | Value |
|---|---|
| `--ease-out` | `cubic-bezier(.2, .8, .2, 1)` |
| `--dur-fast` | 140ms (hover, press) |
| `--dur` | 220ms (page change) |
| `--dur-slow` | 320ms (sheets) |

- Page change: content fades in and rises 6px.
- Sheets slide up on phones and in from the right on desktop; the backdrop fades.
- Buttons press to `scale(.98)`.
- No scroll-triggered fades, parallax or looping decoration.
- Everything is disabled under `prefers-reduced-motion`.

## Components in `components.tsx`
- `Sheet`: modal bottom sheet / desktop side panel.
- `Loading`: skeleton rows plus screen-reader text. Pass `rows` to match the content it stands in for.
- `LoadError`: error with retry.

## Copy
Plain words a shopkeeper would use: "₹450 udhaar likha", not "Transaction created". Errors say what happened and what to do next. Keep English and Hindi catalogs in sync.
