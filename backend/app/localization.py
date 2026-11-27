from enum import StrEnum

from pydantic import BaseModel, Field


class LanguageCode(StrEnum):
    """Supported BCP 47 locale codes."""

    HINDI = "hi-IN"
    ENGLISH_INDIA = "en-IN"


class LanguagePreferences(BaseModel):
    interface_language: LanguageCode = Field(
        default=LanguageCode.HINDI,
        description="Language used for interface labels and transaction templates.",
    )
    speech_language: LanguageCode = Field(
        default=LanguageCode.HINDI,
        description="Language configured for browser speech recognition.",
    )


class VoiceTranscriptRequest(LanguagePreferences):
    original_transcript: str = Field(
        min_length=1,
        description="The exact transcript returned by the speech recognizer.",
    )
