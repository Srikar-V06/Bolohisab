from collections.abc import Sequence

from .language_detector import TranscriptLanguage
from .parser import ClarificationCode, Intent, ParsedAction, PaymentMethod

_EN = TranscriptLanguage.ENGLISH
_HI = TranscriptLanguage.HINDI
_LATN = TranscriptLanguage.HINGLISH

_REVIEW = {
    _EN: "Please review and confirm these details.",
    _HI: "कृपया विवरण जाँचकर पुष्टि करें।",
    _LATN: "Kripya vivaran jaanch kar pushti karein.",
}

_ACTIONS = {
    _EN: {
        Intent.CREDIT: "Record {amount} credit for {name}.",
        Intent.PAYMENT: "Record a {amount} payment from {name}{method}.",
        Intent.BALANCE_QUERY: "Check the outstanding balance for {name}.",
    },
    _HI: {
        Intent.CREDIT: "{name} के खाते में {amount} का उधार लिखें।",
        Intent.PAYMENT: "{name} से {amount} का भुगतान{method} दर्ज करें।",
        Intent.BALANCE_QUERY: "{name} का बकाया देखें।",
    },
    _LATN: {
        Intent.CREDIT: "{name} ke khate mein {amount} udhar likhein.",
        Intent.PAYMENT: "{name} se {amount} ka bhugtan{method} darj karein.",
        Intent.BALANCE_QUERY: "{name} ka bakaya dekhein.",
    },
}

_METHODS = {
    _EN: {PaymentMethod.CASH: " in cash", PaymentMethod.UPI: " via UPI"},
    _HI: {PaymentMethod.CASH: " नकद", PaymentMethod.UPI: " UPI से"},
    _LATN: {PaymentMethod.CASH: " nakad", PaymentMethod.UPI: " UPI se"},
}

_CLARIFICATIONS = {
    _EN: {
        ClarificationCode.MISSING_INTENT: "Say whether you want to record a credit, record a payment, or check a balance.",
        ClarificationCode.MISSING_AMOUNT: "How much should I record?",
        ClarificationCode.INVALID_AMOUNT: "Please repeat the exact amount. For example, say 500 rupees.",
        ClarificationCode.MISSING_CUSTOMER: "Which customer is this for? Please say their name.",
        ClarificationCode.CUSTOMER_NOT_FOUND: "I couldn't find that customer. Please say the name listed in your khata.",
        ClarificationCode.AMBIGUOUS_CUSTOMER: "More than one customer matches. Please say the full name or choose the customer.",
    },
    _HI: {
        ClarificationCode.MISSING_INTENT: "बताइए कि उधार लिखना है, भुगतान दर्ज करना है या बकाया देखना है।",
        ClarificationCode.MISSING_AMOUNT: "कितनी रकम दर्ज करनी है?",
        ClarificationCode.INVALID_AMOUNT: "कृपया सही रकम दोबारा बोलें। जैसे, 500 रुपये।",
        ClarificationCode.MISSING_CUSTOMER: "यह किस ग्राहक के लिए है? कृपया उनका नाम बताइए।",
        ClarificationCode.CUSTOMER_NOT_FOUND: "यह ग्राहक नहीं मिला। कृपया खाते में दर्ज नाम बताइए।",
        ClarificationCode.AMBIGUOUS_CUSTOMER: "एक से ज़्यादा ग्राहक मिले। कृपया पूरा नाम बताइए या ग्राहक चुनिए।",
    },
    _LATN: {
        ClarificationCode.MISSING_INTENT: "Bataiye ki udhar likhna hai, bhugtan darj karna hai ya bakaya dekhna hai.",
        ClarificationCode.MISSING_AMOUNT: "Kitni rakam darj karni hai?",
        ClarificationCode.INVALID_AMOUNT: "Kripya sahi rakam dobara boliye. Jaise, 500 rupaye.",
        ClarificationCode.MISSING_CUSTOMER: "Yeh kis grahak ke liye hai? Kripya unka naam bataiye.",
        ClarificationCode.CUSTOMER_NOT_FOUND: "Yeh grahak nahin mila. Kripya khate mein darj naam bataiye.",
        ClarificationCode.AMBIGUOUS_CUSTOMER: "Ek se zyada grahak mile. Kripya poora naam bataiye ya grahak chunein.",
    },
}


def _format_paise(amount: int) -> str:
    rupees, paise = divmod(amount, 100)
    return f"₹{rupees}.{paise:02d}" if paise else f"₹{rupees}"


def describe_actions(actions: Sequence[ParsedAction], language: TranscriptLanguage) -> str:
    return " ".join(
        _ACTIONS[language][action.intent].format(
            name=action.customer.name,
            amount=_format_paise(action.amount_paise) if action.amount_paise is not None else "",
            method=_METHODS[language].get(action.payment_method, ""),
        )
        for action in actions
    )


def confirmation_message(actions: Sequence[ParsedAction], language: TranscriptLanguage) -> str:
    return _REVIEW[language] + " " + describe_actions(actions, language)


def clarification_message(code: ClarificationCode, language: TranscriptLanguage) -> str:
    return _CLARIFICATIONS[language][code]
