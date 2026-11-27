import re
from unicodedata import normalize

from .ledger import MAX_SQLITE_INTEGER

_CURRENCY_PREFIX = re.compile(r"^(?:₹\s*|(?:inr|rs\.?)\s*(?=\d|\s|$))")
_CURRENCY_SUFFIX = re.compile(r"\s*(?:₹|(?<![a-z])(?:rupees?|rupay[ea]|रुपये|रुपए|रुपया))$")
_DIGITS = re.compile(r"(\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})+,\d{3})(?:\.(\d{1,2}))?")

_SMALL = {
    "ek": 1, "एक": 1, "one": 1,
    "do": 2, "दो": 2, "two": 2,
    "teen": 3, "tin": 3, "तीन": 3, "three": 3,
    "chaar": 4, "char": 4, "चार": 4, "four": 4,
    "paanch": 5, "panch": 5, "पाँच": 5, "पांच": 5, "five": 5,
    "chhe": 6, "chhah": 6, "छह": 6, "छः": 6, "six": 6,
    "saat": 7, "सात": 7, "seven": 7,
    "aath": 8, "आठ": 8, "eight": 8,
    "nau": 9, "नौ": 9, "nine": 9,
    "das": 10, "दस": 10, "ten": 10,
}
_TAILS = {
    **_SMALL,
    "gyarah": 11, "ग्यारह": 11, "eleven": 11,
    "barah": 12, "बारह": 12, "twelve": 12,
    "pandrah": 15, "पंद्रह": 15, "fifteen": 15,
    "bees": 20, "बीस": 20, "twenty": 20,
    "pachis": 25, "pachchis": 25, "पच्चीस": 25,
    "tees": 30, "तीस": 30, "thirty": 30,
    "chalis": 40, "chaalis": 40, "चालीस": 40, "forty": 40,
    "pachas": 50, "pachaas": 50, "पचास": 50, "fifty": 50,
    "saath": 60, "साठ": 60, "sixty": 60,
    "sattar": 70, "सत्तर": 70, "seventy": 70,
    "assi": 80, "अस्सी": 80, "eighty": 80,
    "nabbe": 90, "नब्बे": 90, "ninety": 90,
}
_HUNDREDS = {"sau", "so", "सौ", "hundred"}
_QUARTERS = {
    "sawa": 25, "sava": 25, "सवा": 25,
    "saadhe": 50, "sadhe": 50, "साढ़े": 50,
    "paune": -25, "paunay": -25, "पौने": -25,
}
_ONE_AND_A_HALF = {"dedh", "derh", "डेढ़"}


class AmountError(ValueError):
    def __init__(self, *, missing: bool = False) -> None:
        self.missing = missing
        super().__init__("Missing amount" if missing else "Unclear or invalid amount")


def _spoken_rupees(text: str) -> int | None:
    words = text.split()
    if text in _TAILS:
        return _TAILS[text]
    hundreds = [i for i, word in enumerate(words) if word in _HUNDREDS]
    if len(hundreds) != 1:
        return None
    position = hundreds[0]
    head, tail = words[:position], words[position + 1:]
    if not head and not tail:
        return 100
    if len(head) == 1:
        if not tail and head[0] in _ONE_AND_A_HALF:
            return 150
        if not tail and head[0] in {"sawa", "sava", "सवा"}:
            return 125
        multiple = _SMALL.get(head[0])
        if multiple is not None:
            if not tail:
                return multiple * 100
            remainder = " ".join(tail)
            if remainder in _TAILS:
                return multiple * 100 + _TAILS[remainder]
    if len(head) == 2 and not tail and head[0] in _QUARTERS and head[1] in _SMALL:
        return _SMALL[head[1]] * 100 + _QUARTERS[head[0]]
    return None


def parse_amount_paise(expression: str) -> int:
    """Parse a complete amount expression and return exact, positive integer paise."""
    value = " ".join(normalize("NFC", expression).casefold().split())
    value = _CURRENCY_PREFIX.sub("", value)
    value = _CURRENCY_SUFFIX.sub("", value).strip()
    if not value:
        raise AmountError(missing=True)

    numeric = _DIGITS.fullmatch(value)
    if numeric:
        whole, fraction = numeric.groups()
        digits = whole.replace(",", "")
        if len(digits) > 17:
            raise AmountError()
        paise = int(digits) * 100 + int((fraction or "").ljust(2, "0"))
    else:
        rupees = _spoken_rupees(value)
        if rupees is None:
            raise AmountError()
        paise = rupees * 100
    if not 1 <= paise <= MAX_SQLITE_INTEGER:
        raise AmountError()
    return paise
