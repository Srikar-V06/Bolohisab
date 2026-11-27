from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import AliasChoices, ConfigDict, Field

from .database import DEFAULT_SHOP_ID
from .language_detector import TranscriptLanguage, detect_language
from .ledger import CustomerIdentity, ledger_session
from .localization import VoiceTranscriptRequest
from .localized_messages import clarification_message, confirmation_message, describe_actions
from .parser import ClarificationCode, ClarificationRequired, ParsedAction, parse_transcript

router = APIRouter(prefix="/api/voice", tags=["voice"])


class VoiceParseRequest(VoiceTranscriptRequest):
    model_config = ConfigDict(extra="forbid")
    original_transcript: str = Field(
        min_length=1,
        max_length=4096,
        validation_alias=AliasChoices("original_transcript", "transcript"),
        description="The exact transcript returned by the speech recognizer.",
    )


@dataclass(frozen=True)
class VoiceClarification:
    code: ClarificationCode
    clause_index: int
    candidates: tuple[CustomerIdentity, ...]


@dataclass(frozen=True)
class VoiceParseResult:
    original_transcript: str
    detected_language: TranscriptLanguage | None
    status: Literal["REVIEW_REQUIRED", "CLARIFICATION_REQUIRED"]
    requires_confirmation: bool
    actions: list[ParsedAction]
    english_interpretation: str | None = None
    confirmation_message: str | None = None
    clarification_message: str | None = None
    clarification: VoiceClarification | None = None


@router.post("/parse")
def parse_voice(payload: VoiceParseRequest, request: Request) -> VoiceParseResult:
    transcript = payload.original_transcript
    language = detect_language(transcript)
    message_language = language or TranscriptLanguage(payload.interface_language)
    with ledger_session(request.app.state.database_path) as ledger:
        customers = ledger.list_customer_names(DEFAULT_SHOP_ID)

    try:
        actions = parse_transcript(transcript, customers)
    except ClarificationRequired as error:
        return VoiceParseResult(
            original_transcript=transcript,
            detected_language=language,
            status="CLARIFICATION_REQUIRED",
            requires_confirmation=False,
            actions=[],
            clarification_message=clarification_message(error.code, message_language),
            clarification=VoiceClarification(error.code, error.clause_index, error.candidates),
        )

    return VoiceParseResult(
        original_transcript=transcript,
        detected_language=language,
        status="REVIEW_REQUIRED",
        requires_confirmation=True,
        actions=actions,
        english_interpretation=describe_actions(actions, TranscriptLanguage.ENGLISH),
        confirmation_message=confirmation_message(actions, message_language),
    )
