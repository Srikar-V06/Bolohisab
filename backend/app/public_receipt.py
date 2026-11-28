from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from secrets import token_urlsafe

from fastapi.responses import HTMLResponse

from .localization import LanguageCode
from .receipt_store import ReceiptItem


COPY = {
    LanguageCode.HINDI: {
        "title": "रसीद",
        "fields": ("ग्राहक", "लेन-देन आईडी", "तारीख़ और समय", "लेन-देन", "रकम", "लेन-देन के बाद बकाया"),
        "types": {"CREDIT": "उधार", "PAYMENT": "भुगतान", "ADJUSTMENT": "समायोजन"},
        "methods": {"CASH": "नकद", "UPI": "UPI"},
        "language": "रसीद की भाषा",
        "listen": "रसीद सुनें",
        "stop": "सुनना बंद करें",
        "unavailable": "इस डिवाइस पर चुनी गई भाषा में रसीद सुनना उपलब्ध नहीं है।",
        "confirm": "लेन-देन की पुष्टि करें",
        "report": "लेन-देन में गड़बड़ी बताएँ",
        "claim": "आपके हिसाब से सही रकम (₹)",
        "reason": "क्या गड़बड़ी है?",
        "submit": "सुधार का अनुरोध भेजें",
        "confirmed": "आपने इस लेन-देन की पुष्टि कर दी है।",
        "dispute": {
            "PENDING": "सुधार का अनुरोध भेज दिया गया है। दुकानदार इसकी जाँच करेंगे।",
            "APPROVED": "दुकानदार ने आपका सुधार स्वीकार कर लिया है और खाते में समायोजन जोड़ दिया है।",
            "REJECTED": "दुकानदार ने सुधार का अनुरोध अस्वीकार कर दिया है।",
        },
        "not_found": "यह रसीद नहीं मिली। दुकानदार से सही लिंक माँगें।",
        "invalid": "अलग सही रकम लिखें। रुपये में दशमलव के बाद अधिकतम दो अंक दें।",
        "conflict": "इस रसीद पर पहले ही जवाब दिया जा चुका है। नया जवाब देखने के लिए पेज फिर से खोलें।",
        "failed": "जवाब भेजा नहीं जा सका। दोबारा कोशिश करें।",
        "noscript": "रसीद सुनने या जवाब देने के लिए ब्राउज़र में JavaScript चालू करें।",
    },
    LanguageCode.ENGLISH_INDIA: {
        "title": "Receipt",
        "fields": ("Customer", "Transaction ID", "Date and time", "Transaction", "Amount", "Balance after transaction"),
        "types": {"CREDIT": "Credit", "PAYMENT": "Payment", "ADJUSTMENT": "Adjustment"},
        "methods": {"CASH": "Cash", "UPI": "UPI"},
        "language": "Receipt language",
        "listen": "Listen to receipt",
        "stop": "Stop playback",
        "unavailable": "Receipt playback in this language is unavailable on this device.",
        "confirm": "Confirm transaction",
        "report": "Report a discrepancy",
        "claim": "Correct amount (₹)",
        "reason": "What is different?",
        "submit": "Send correction request",
        "confirmed": "You confirmed this transaction.",
        "dispute": {
            "PENDING": "Your correction request was sent. The shopkeeper will review it.",
            "APPROVED": "The shopkeeper accepted your correction and added an adjustment to the ledger.",
            "REJECTED": "The shopkeeper rejected your correction request.",
        },
        "not_found": "This receipt could not be found. Ask the shopkeeper for the correct link.",
        "invalid": "Enter a different amount in rupees, with up to two decimal places.",
        "conflict": "This receipt already has a response. Reload the page to see it.",
        "failed": "Your response could not be sent. Try again.",
        "noscript": "Enable JavaScript in your browser to listen or respond.",
    },
}

STYLE = Path(__file__).with_name("public_receipt.css").read_text(encoding="utf-8")
SCRIPT = Path(__file__).with_name("public_receipt.js").read_text(encoding="utf-8")
INDIA = timezone(timedelta(hours=5, minutes=30), "IST")


def _money(paise: int) -> str:
    whole, fraction = divmod(abs(paise), 100)
    amount = f"{whole}.{fraction:02d}" if fraction else str(whole)
    return ("−" if paise < 0 else "") + "₹" + amount


def _receipt_content(item: ReceiptItem, copy: dict) -> str:
    kind = copy["types"][item.type]
    method = copy["methods"].get(item.payment_method)
    if method:
        kind = f"{kind} · {method}"
    date = datetime.fromisoformat(item.created_at).astimezone(INDIA)
    values = (item.customer_name, str(item.entry_id), date.strftime("%d/%m/%Y %H:%M IST"), kind,
              _money(item.amount_paise), _money(item.balance_after_paise))
    rows = "".join(
        f"<div><dt>{label}</dt><dd>{escape(value)}</dd></div>"
        for label, value in zip(copy["fields"], values, strict=True)
    )
    return f"""<article id="receipt">
        <h1>{copy['title']}</h1><p class="shop">{escape(item.shop_name)}</p><dl>{rows}</dl>
    </article>
    <button class="secondary" type="button" id="listen" data-start="{copy['listen']}"
        data-stop="{copy['stop']}" data-unavailable="{copy['unavailable']}">{copy['listen']}</button>
    <p id="playback-status" role="status"></p>"""


def _customer_actions(item: ReceiptItem, copy: dict) -> str:
    if item.dispute:
        return f'<p class="notice">{copy["dispute"][item.dispute.status]}</p>'
    if item.confirmed_at:
        return f'<p class="notice">{copy["confirmed"]}</p>'
    return f"""<section id="response-actions" data-invalid="{copy['invalid']}" data-conflict="{copy['conflict']}"
        data-failed="{copy['failed']}">
        <button type="button" id="confirm">{copy['confirm']}</button>
        <details>
            <summary>{copy['report']}</summary>
            <form id="dispute" method="post">
                <label for="claim">{copy['claim']}</label>
                <input id="claim" type="text" inputmode="decimal" maxlength="25" required>
                <label for="reason">{copy['reason']}</label>
                <textarea id="reason" rows="3" maxlength="500" required></textarea>
                <button type="submit">{copy['submit']}</button>
            </form>
        </details>
        <p id="action-status" role="alert"></p>
    </section>"""


def render_shared_receipt(item: ReceiptItem | None, language: LanguageCode | None) -> HTMLResponse:
    locale = language or (item.language if item else None) or LanguageCode.HINDI
    copy = COPY[locale]
    nonce = token_urlsafe(18)
    if item:
        links = []
        for code, label in ((LanguageCode.HINDI, "हिन्दी"), (LanguageCode.ENGLISH_INDIA, "English")):
            current = ' aria-current="true"' if locale == code else ""
            links.append(f'<a href="?language={code}" lang="{code}"{current}>{label}</a>')
        content = (f'<nav aria-label="{copy["language"]}">{"".join(links)}</nav>'
                   + _receipt_content(item, copy) + _customer_actions(item, copy))
    else:
        content = f"<h1>{copy['title']}</h1><p>{copy['not_found']}</p>"
    return HTMLResponse(
        f"""<!doctype html>
        <html lang="{locale}"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>{copy['title']} · BoloHisaab</title><style nonce="{nonce}">{STYLE}</style>
        </head><body><main>{content}<noscript><p>{copy['noscript']}</p></noscript></main>
        <script nonce="{nonce}">{SCRIPT}</script></body></html>""",
        status_code=200 if item else 404,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": (
                f"default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; "
                "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            ),
        },
    )
