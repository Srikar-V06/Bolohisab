import re
from enum import StrEnum
from unicodedata import category, normalize


class TranscriptLanguage(StrEnum):
    HINDI = "hi-IN"
    HINGLISH = "hi-Latn-IN"
    ENGLISH = "en-IN"


_ROMAN_HINDI = re.compile(
    r"\b(?:khate|khaate|khata|khaata|rupaye|rupaya|udhar|udhaar|likh|diya|diye|usne|"
    r"unhone|batao|kitna|baki|baaki|bakaya|sau|dedh|saadhe|paune|nakad|nagad|jama)\b"
)
_ENGLISH_COMMAND = re.compile(
    r"^(?:please\s+)?(?:record|log|add|received|show|check|tell me|what|balance)\b|\bpaid\b"
)


def detect_language(transcript: str) -> TranscriptLanguage | None:
    text = " ".join(normalize("NFC", transcript).casefold().split())
    if _ENGLISH_COMMAND.search(text):
        return TranscriptLanguage.ENGLISH
    if any("\u0900" <= char <= "\u097f" and category(char).startswith("L") for char in text):
        return TranscriptLanguage.HINDI
    if _ROMAN_HINDI.search(text) or re.search(r"\b(?:ke|ka)\s+(?:balance|hisab|hisaab|paise)\b", text):
        return TranscriptLanguage.HINGLISH
    if re.search(r"[a-z]", text):
        return TranscriptLanguage.ENGLISH
    return None
