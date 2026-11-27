import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from unicodedata import normalize

from .ledger import MAX_SQLITE_INTEGER, CustomerIdentity
from .number_parser import AmountError, parse_amount_paise


class Intent(StrEnum):
    CREDIT = "CREDIT"
    PAYMENT = "PAYMENT"
    BALANCE_QUERY = "BALANCE_QUERY"


class PaymentMethod(StrEnum):
    CASH = "CASH"
    UPI = "UPI"


class ClarificationCode(StrEnum):
    MISSING_INTENT = "MISSING_INTENT"
    MISSING_AMOUNT = "MISSING_AMOUNT"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    MISSING_CUSTOMER = "MISSING_CUSTOMER"
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    AMBIGUOUS_CUSTOMER = "AMBIGUOUS_CUSTOMER"


class ClarificationRequired(ValueError):
    def __init__(
        self, code: ClarificationCode, clause_index: int,
        candidates: Sequence[CustomerIdentity] = (),
    ) -> None:
        self.code = code
        self.clause_index = clause_index
        self.candidates = tuple(candidates)
        super().__init__(code.value)


@dataclass(frozen=True)
class UnresolvedAction:
    intent: Intent
    customer_name: str | None = None
    amount_paise: int | None = None
    payment_method: PaymentMethod | None = None
    refers_to_previous_customer: bool = False


@dataclass(frozen=True)
class ParsedAction:
    intent: Intent
    customer: CustomerIdentity
    amount_paise: int | None
    payment_method: PaymentMethod | None


class VoiceUnderstandingAdapter(Protocol):
    """An optional provider proposes actions without customer IDs or write access."""

    def interpret(self, transcript: str) -> Sequence[UnresolvedAction] | None:
        """Return draft actions or decline to interpret the transcript."""
        ...


_NAME = r"(?P<name>.+?)"
_AMOUNT = r"(?P<amount>.*?)"
_ACCOUNT = r"(?:ke kha?ate (?:mein|me|main)|के खाते में)"
_WRITE = r"(?:likh (?:do|dijiye)|लिख (?:दो|दें|दीजिए))"
_CREDIT = r"(?:udha?ar|उधार)"
_GAVE = r"(?:diya|diye|di|jama kiye|दिया|दिए|दिये|दी|जमा किए)(?: (?:hai|hain|है|हैं))?"
_CASH = {"cash", "nakad", "nagad", "नकद", "नगद", "कैश"}
_UPI = {"upi", "u p i", "यूपीआई", "यू पी आई"}
_METHOD = r"(?P<method>" + "|".join(sorted(_CASH | _UPI)) + r")"
_EN_METHOD = rf"(?: (?:by|via|in|with) {_METHOD})?"
_EN_RECORD = r"(?:record|log|add) (?:a )?"
_PRONOUNS = {"he", "she", "they", "him", "her", "them", "usne", "unhone", "उसने", "उन्होंने"}
_SPLIT_CLAUSES = re.compile(r" *[;।] *| +(?:aur|और|and(?: then)?) +", re.IGNORECASE)

_RULES = (
    (Intent.CREDIT, rf"(?:{_NAME} {_ACCOUNT} )?{_AMOUNT}\s*{_CREDIT} {_WRITE}"),
    (Intent.CREDIT, rf"(?:{_NAME} )?{_ACCOUNT} (?:(?P<amount>.+?) )?{_WRITE}"),
    (Intent.CREDIT, rf"{_EN_RECORD}{_AMOUNT}\s*credit(?: for {_NAME})?"),
    (Intent.CREDIT, rf"{_EN_RECORD}credit(?: of (?P<amount>.+?))?(?: for {_NAME})?"),
    (Intent.PAYMENT, rf"{_EN_RECORD}{_AMOUNT}\s*payment(?: for {_NAME})?{_EN_METHOD}"),
    (Intent.PAYMENT, rf"{_EN_RECORD}payment(?: of (?P<amount>.+?))?(?: for {_NAME})?{_EN_METHOD}"),
    (Intent.PAYMENT, rf"{_NAME} paid(?: (?P<amount>.+?))??{_EN_METHOD}"),
    (Intent.PAYMENT, rf"received {_AMOUNT}\s*from {_NAME}{_EN_METHOD}"),
    (
        Intent.PAYMENT,
        rf"(?:(?:{_NAME} (?:ne|ने)|(?P<pronoun>usne|unhone|उसने|उन्होंने)) )?"
        rf"{_AMOUNT}\s*(?:{_METHOD} (?:(?:se|से|mein|में) )?)?{_GAVE}",
    ),
    (
        Intent.BALANCE_QUERY,
        rf"(?:(?:show|check|tell me|what(?:['’]s| is)) )?(?:the )?(?:outstanding )?"
        rf"balance(?: (?:for|of) {_NAME})?",
    ),
    (Intent.BALANCE_QUERY, rf"(?:what(?:['’]s| is) )?{_NAME}['’]s (?:outstanding )?balance"),
    (
        Intent.BALANCE_QUERY,
        rf"(?:{_NAME} (?:ka|ke|का|के) )?(?:balance|ba?aki|bakaya|बकाया|बाकी) "
        r"(?:batao|बताओ|बताइए|kitna hai|कितना है)",
    ),
    (
        Intent.BALANCE_QUERY,
        rf"{_NAME} (?:ka|का) (?:kitna|कितना) (?:balance|ba?aki|bakaya|बकाया|बाकी) (?:hai|है)",
    ),
)
_GRAMMAR = tuple((intent, re.compile(rule, re.IGNORECASE)) for intent, rule in _RULES)

# Explicit cross-script spelling equivalents. The stored customer name is returned verbatim.
_NAME_EQUIVALENTS = {
    "रमेश": "ramesh", "सुरेश": "suresh", "सीता": "sita", "seeta": "sita",
    "प्रिया": "priya", "सुनीता": "sunita", "अमित": "amit",
    "शर्मा": "sharma", "कुमार": "kumar", "यादव": "yadav", "गुप्ता": "gupta", "वर्मा": "verma",
}


def _name_key(name: str) -> tuple[str, ...]:
    words = normalize("NFC", name).casefold().split()
    return tuple(_NAME_EQUIVALENTS.get(word, word) for word in words)


def _recognize_clause(clause: str, index: int) -> UnresolvedAction:
    clause = re.sub(r"^(?:please|कृपया) ", "", clause, flags=re.IGNORECASE)
    clause = re.sub(r" (?:please|कृपया)$", "", clause, flags=re.IGNORECASE)
    for intent, rule in _GRAMMAR:
        match = rule.fullmatch(clause)
        if not match:
            continue

        fields = match.groupdict()
        name = fields.get("name")
        refers_to_previous = fields.get("pronoun") is not None
        if name and name.casefold() in _PRONOUNS:
            name = None
            refers_to_previous = True
        if intent == Intent.BALANCE_QUERY:
            return UnresolvedAction(intent, name, refers_to_previous_customer=refers_to_previous)
        try:
            amount = parse_amount_paise(fields.get("amount") or "")
        except AmountError as error:
            code = ClarificationCode.MISSING_AMOUNT if error.missing else ClarificationCode.INVALID_AMOUNT
            raise ClarificationRequired(code, index) from error

        method_text = fields.get("method")
        method = None
        if method_text:
            method = PaymentMethod.CASH if method_text.casefold() in _CASH else PaymentMethod.UPI
        return UnresolvedAction(intent, name, amount, method, refers_to_previous)
    raise ClarificationRequired(ClarificationCode.MISSING_INTENT, index)


# Word-order-free fallback vocabulary. A credit word wins over a "gave" verb: "udhaar diya" is a credit.
_CREDIT_WORDS = {"credit", "udhaar", "udhar", "udhaari", "उधार", "उधारी"}
_PAYMENT_WORDS = {
    "paid", "pay", "pays", "payment", "received", "receive", "got", "returned", "deposited",
    "diya", "diye", "di", "jama", "lautaye", "दिया", "दिए", "दिये", "दी", "जमा", "लौटाए",
}
_FILLER = {
    "to", "for", "from", "of", "on", "by", "via", "in", "at", "with", "me", "my", "a", "an", "the",
    "record", "add", "log", "entry", "give", "gave", "given", "took", "take", "taken", "has", "have",
    "is", "was", "please", "ko", "ne", "se", "ka", "ke", "ki", "mein", "main", "hai", "hain", "tha",
    "को", "ने", "से", "का", "के", "की", "में", "है", "हैं", "था", "khate", "khata", "खाते", "खाता",
    "account", "ji", "जी", "kar", "karo", "कर", "करो",
    "open", "create", "make", "new", "write", "note", "put", "enter", "mark", "an", "amount",
}
_NEGATION = {"not", "don't", "dont", "no", "cancel", "mat", "nahi", "nahin", "मत", "नहीं", "ना"}
_WRITE_PHRASE = re.compile(rf"\b{_WRITE}|\b(?:de|दे) (?:do|diya|दो|दिया)\b", re.IGNORECASE)


def _amount_window(words: list[str]) -> tuple[int, int, int] | None:
    """The longest run of words that reads as one amount, or None when absent or ambiguous."""
    found: list[tuple[int, int, int]] = []
    for size in range(len(words), 0, -1):
        for start in range(len(words) - size + 1):
            try:
                found.append((start, start + size, parse_amount_paise(" ".join(words[start:start + size]))))
            except AmountError:
                pass
        if found:
            break
    return found[0] if len(found) == 1 else None


def _fill_slots(clause: str, customers: Sequence[CustomerIdentity]) -> UnresolvedAction | None:
    """Read intent, amount, method and a known customer from a clause in any word order."""
    text = _WRITE_PHRASE.sub(" ", clause)
    words = [word.strip(",.?!:") for word in text.split()]
    words = [word for word in words if word]
    folded = [word.casefold() for word in words]
    if any(word in _NEGATION for word in folded):
        return None
    if any(word in _CREDIT_WORDS for word in folded):
        intent = Intent.CREDIT
    elif any(word in _PAYMENT_WORDS for word in folded):
        intent = Intent.PAYMENT
    else:
        return None
    method = None
    if intent == Intent.PAYMENT:
        if any(word in _CASH for word in folded):
            method = PaymentMethod.CASH
        elif any(word in _UPI for word in folded):
            method = PaymentMethod.UPI

    # The longest span of words that starts a known customer's name, e.g. "Ramesh" or "Ramesh Kumar".
    name_span: tuple[int, int] | None = None
    keys = [_name_key(customer.name) for customer in customers]
    for start in range(len(words)):
        for end in range(len(words), start, -1):
            span = _name_key(" ".join(words[start:end]))
            if any(key[: len(span)] == span for key in keys) and (
                    name_span is None or end - start > name_span[1] - name_span[0]):
                name_span = (start, end)
                break

    vocabulary = _CREDIT_WORDS | _PAYMENT_WORDS | _FILLER | _CASH | _UPI
    rest = [i for i, word in enumerate(folded)
            if word not in vocabulary and not (name_span and name_span[0] <= i < name_span[1])]
    if name_span:
        # With a known customer, every remaining word must be the amount; nothing is guessed or skipped.
        try:
            amount = parse_amount_paise(" ".join(words[i] for i in rest))
        except AmountError:
            return None
        name = " ".join(words[name_span[0]:name_span[1]])
    else:
        window = _amount_window([words[i] for i in rest])
        if window is None:
            return None
        start, end, amount = window
        # Unknown words left over are the spoken name; resolution reports it as not found.
        leftover = [words[i] for position, i in enumerate(rest) if not start <= position < end]
        name = " ".join(leftover) or None
    if name and name.casefold() in _PRONOUNS:
        return UnresolvedAction(intent, None, amount, method, refers_to_previous_customer=True)
    return UnresolvedAction(intent, name, amount, method)


def _recognize(transcript: str, customers: Sequence[CustomerIdentity] = ()) -> tuple[UnresolvedAction, ...]:
    text = " ".join(normalize("NFC", transcript).split())
    text = text.removesuffix("।").strip()
    actions = []
    for index, clause in enumerate(_SPLIT_CLAUSES.split(text), start=1):
        clause = clause.strip().removesuffix(".").removesuffix("?").strip()
        try:
            actions.append(_recognize_clause(clause, index))
        except ClarificationRequired as error:
            if error.code not in (ClarificationCode.MISSING_INTENT, ClarificationCode.MISSING_AMOUNT,
                                  ClarificationCode.INVALID_AMOUNT):
                raise
            fallback = _fill_slots(clause, customers)
            if fallback is None:
                raise
            actions.append(fallback)
    return tuple(actions)


def _resolve_customer(
    draft: UnresolvedAction, customers: Sequence[CustomerIdentity],
    previous: dict[int, CustomerIdentity], index: int,
) -> CustomerIdentity:
    name = draft.customer_name
    if not name or not name.strip():
        if draft.refers_to_previous_customer is not True or not previous:
            raise ClarificationRequired(ClarificationCode.MISSING_CUSTOMER, index)
        if len(previous) == 1:
            return next(iter(previous.values()))
        raise ClarificationRequired(ClarificationCode.AMBIGUOUS_CUSTOMER, index, list(previous.values()))

    key = _name_key(name)
    matches = [customer for customer in customers if _name_key(customer.name)[: len(key)] == key]
    if not matches:
        raise ClarificationRequired(ClarificationCode.CUSTOMER_NOT_FOUND, index)
    if len(matches) != 1:
        raise ClarificationRequired(ClarificationCode.AMBIGUOUS_CUSTOMER, index, matches)
    return matches[0]


def parse_transcript(
    transcript: str, customers: Sequence[CustomerIdentity], *,
    adapter: VoiceUnderstandingAdapter | None = None,
) -> list[ParsedAction]:
    """Interpret the whole transcript and resolve each name within the shop's directory."""
    proposed = adapter.interpret(transcript) if adapter is not None else None
    drafts = tuple(proposed) if proposed is not None else _recognize(transcript, customers)
    if not drafts:
        raise ClarificationRequired(ClarificationCode.MISSING_INTENT, 1)

    actions: list[ParsedAction] = []
    previous: dict[int, CustomerIdentity] = {}
    for index, draft in enumerate(drafts, start=1):
        if not isinstance(draft, UnresolvedAction) or not isinstance(draft.intent, Intent):
            raise ClarificationRequired(ClarificationCode.MISSING_INTENT, index)
        if draft.intent != Intent.PAYMENT and draft.payment_method is not None:
            raise ClarificationRequired(ClarificationCode.MISSING_INTENT, index)
        if draft.payment_method is not None and not isinstance(draft.payment_method, PaymentMethod):
            raise ClarificationRequired(ClarificationCode.MISSING_INTENT, index)
        if draft.intent == Intent.BALANCE_QUERY:
            if draft.amount_paise is not None:
                raise ClarificationRequired(ClarificationCode.MISSING_INTENT, index)
        elif draft.amount_paise is None:
            raise ClarificationRequired(ClarificationCode.MISSING_AMOUNT, index)
        elif type(draft.amount_paise) is not int or not 1 <= draft.amount_paise <= MAX_SQLITE_INTEGER:
            raise ClarificationRequired(ClarificationCode.INVALID_AMOUNT, index)
        if draft.customer_name is not None and not isinstance(draft.customer_name, str):
            raise ClarificationRequired(ClarificationCode.MISSING_CUSTOMER, index)

        customer = _resolve_customer(draft, customers, previous, index)
        previous[customer.id] = customer
        actions.append(ParsedAction(draft.intent, customer, draft.amount_paise, draft.payment_method))
    return actions
