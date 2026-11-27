"""Optional on-device understanding through a local Ollama model.

The model only points at words in the transcript: which intent, which words name the customer and
which words are the amount. The app's own number parser turns the amount words into paise, names are
resolved against the shop's customers, and the shopkeeper still reviews every entry before saving.
"""
import json
import logging
import re
import urllib.error
import urllib.request
from functools import lru_cache
from os import environ
from unicodedata import normalize

from .number_parser import _CURRENCY_PREFIX, _CURRENCY_SUFFIX, AmountError, parse_amount_paise
from .parser import _CASH, _PRONOUNS, _UPI, Intent, PaymentMethod, UnresolvedAction

log = logging.getLogger(__name__)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

_SCHEMA = {
    "type": "object",
    "properties": {"actions": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": [intent.value for intent in Intent]},
            "customer_words": {"type": ["string", "null"]},
            "amount_words": {"type": ["string", "null"]},
            "method_words": {"type": ["string", "null"]},
        },
        "required": ["intent", "customer_words", "amount_words", "method_words"],
    }}},
    "required": ["actions"],
}

_INSTRUCTIONS = (
    "You read one sentence a shopkeeper spoke to their ledger app, in English, Hindi or Hinglish, "
    "and return its actions as JSON.\n"
    "intent: CREDIT when the customer took goods or money on credit (udhaar), so their dues go up; "
    "PAYMENT when the customer paid or returned money, so their dues go down; "
    "BALANCE_QUERY when asking how much a customer owes.\n"
    "customer_words: the customer's name copied exactly as written in the sentence, without words like "
    "ko, ne, ka, bhaiya or ji. Use null if no name is said.\n"
    "amount_words: the amount copied character for character from the sentence, digits or words, "
    "e.g. '450' or 'साढ़े चार सौ'. Do not add Rs or ₹ and never convert or calculate. Use null for a balance question or if no "
    "amount is said. If two amounts are said for one payment, use the amount actually paid.\n"
    "method_words: 'cash', 'nakad', 'UPI' etc. only if that word is in the sentence, otherwise null.\n"
    "Each customer transaction is one action. Return no actions if the sentence is not a ledger instruction."
)


def _fold(text: str) -> str:
    return " ".join(normalize("NFC", text).casefold().split())


class LocalModelAdapter:
    """Proposes actions from a local model. Anything not literally in the transcript is dropped."""

    def __init__(self, model: str, url: str = "http://127.0.0.1:11434", timeout: float = 30) -> None:
        self.model, self.url, self.timeout = model, url.rstrip("/"), timeout

    def _ask(self, transcript: str) -> list[dict]:
        body = json.dumps({
            "model": self.model, "stream": False, "format": _SCHEMA, "keep_alive": "30m",
            "options": {"temperature": 0, "seed": 7},
            "messages": [{"role": "system", "content": _INSTRUCTIONS}, {"role": "user", "content": transcript}],
        }).encode()
        request = urllib.request.Request(self.url + "/api/chat", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(json.load(response)["message"]["content"])["actions"]

    def warm(self) -> None:
        """Ask Ollama to load the model now; failure just means rules-only until it is running."""
        request = urllib.request.Request(self.url + "/api/generate", json.dumps(
            {"model": self.model, "keep_alive": "30m"}).encode(), {"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(request, timeout=120).close()
        except OSError as error:
            log.warning("Local model %s not loaded: %s", self.model, error)

    def interpret(self, transcript: str) -> tuple[UnresolvedAction, ...] | None:
        """Model proposals, or None when the model declines, is unsure or is not running."""
        try:
            return _cached_interpretation(self, transcript)
        except _Unavailable:
            return None

    def to_actions(self, transcript: str, proposals: list[dict]) -> tuple[UnresolvedAction, ...] | None:
        said = _fold(transcript)
        actions = []
        for proposal in proposals:
            try:
                intent = Intent(proposal["intent"])
            except (KeyError, TypeError, ValueError):
                return None
            name = (proposal.get("customer_words") or "").strip() or None
            amount_text = (proposal.get("amount_words") or "").strip()
            method_text = _fold(proposal.get("method_words") or "")
            # Hallucination guard: the name and amount must be words the shopkeeper said. A currency
            # marker the model adds ("Rs 200" for "200") is not a new fact, so it is ignored here.
            amount_core = _CURRENCY_SUFFIX.sub("", _CURRENCY_PREFIX.sub("", _fold(amount_text))).strip()
            if any(part and _fold(part) not in said for part in (name, amount_core)):
                return None
            if method_text and method_text not in said:
                method_text = ""  # An unsaid payment method is dropped, never recorded.
            amount = None
            if amount_text and intent != Intent.BALANCE_QUERY:
                try:
                    amount = parse_amount_paise(amount_text)
                except AmountError:
                    return None
            method = None
            if intent == Intent.PAYMENT and method_text:
                method = (PaymentMethod.CASH if method_text in _CASH
                          else PaymentMethod.UPI if method_text in _UPI else None)
            pronoun = name is not None and name.casefold() in _PRONOUNS
            actions.append(UnresolvedAction(intent, None if pronoun else name, amount, method, pronoun))
        # More numbers said than amounts used means the model picked one ("500 mein se 200"): ask again.
        numbers = set(_NUMBER.findall(said))
        if len(numbers) > sum(action.amount_paise is not None for action in actions):
            return None
        return tuple(actions) or None


# The confirm step re-reads the transcript; caching keeps that second reading identical to the review.
@lru_cache(maxsize=512)
def _cached_interpretation(adapter: LocalModelAdapter, transcript: str) -> tuple[UnresolvedAction, ...] | None:
    try:
        proposals = adapter._ask(transcript)
    except (OSError, urllib.error.URLError, ValueError, KeyError, TypeError) as error:
        log.warning("Local model unavailable, using rules only: %s", error)
        raise _Unavailable() from error
    return adapter.to_actions(transcript, proposals)


class _Unavailable(Exception):
    """Raised so a failed call is not cached; the next request tries the model again."""


def configured_model() -> LocalModelAdapter | None:
    """BOLO_LOCAL_MODEL picks the Ollama model (default qwen2.5:3b); set it empty to turn this off."""
    model = environ.get("BOLO_LOCAL_MODEL", "qwen2.5:3b").strip()
    if not model:
        return None
    return LocalModelAdapter(model, environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
