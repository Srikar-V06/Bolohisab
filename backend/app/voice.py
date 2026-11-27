from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, StrictInt

from .database import DEFAULT_SHOP_ID
from .language_detector import TranscriptLanguage, detect_language
from .ledger import (
    MAX_SQLITE_INTEGER, CustomerIdentity, Ledger, LedgerEntryDraft, PaymentMethodCode,
    TransactionBatch, ledger_session,
)
from .localization import VoiceTranscriptRequest
from .localized_messages import clarification_message, confirmation_message, describe_actions
from .parser import ClarificationCode, ClarificationRequired, Intent, ParsedAction, parse_transcript

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
class BalancePreview:
    customer: CustomerIdentity
    previous_balance_paise: int
    updated_balance_paise: int
    credit_paise: int
    payment_paise: int


@dataclass(frozen=True)
class VoiceParseResult:
    original_transcript: str
    detected_language: TranscriptLanguage | None
    status: Literal["REVIEW_REQUIRED", "CLARIFICATION_REQUIRED"]
    requires_confirmation: bool
    actions: list[ParsedAction]
    balances: tuple[BalancePreview, ...] = ()
    english_interpretation: str | None = None
    confirmation_message: str | None = None
    clarification_message: str | None = None
    clarification: VoiceClarification | None = None


class ConfirmAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: Annotated[int, Field(strict=True, ge=1, le=MAX_SQLITE_INTEGER)]
    intent: Literal["CREDIT", "PAYMENT"]
    amount_paise: Annotated[int, Field(strict=True, ge=1, le=MAX_SQLITE_INTEGER)]
    payment_method: PaymentMethodCode | None = None


class VoiceConfirmRequest(VoiceParseRequest):
    batch_id: UUID
    actions: list[ConfirmAction] = Field(min_length=1, max_length=128)
    previous_balances: dict[int, StrictInt]


def _ledger_drafts(actions: list[ParsedAction]) -> tuple[LedgerEntryDraft, ...]:
    return tuple(
        LedgerEntryDraft(
            action.customer.id,
            "CREDIT" if action.intent == Intent.CREDIT else "PAYMENT",
            action.amount_paise,
            payment_method=action.payment_method,
        )
        for action in actions if action.intent != Intent.BALANCE_QUERY and action.amount_paise is not None
    )


def _balance_previews(ledger: Ledger, actions: list[ParsedAction]) -> tuple[BalancePreview, ...]:
    customers = {action.customer.id: action.customer for action in actions}
    drafts = _ledger_drafts(actions)
    previews = []
    for customer in customers.values():
        previous = ledger.calculate_balance(DEFAULT_SHOP_ID, customer.id)
        entries = [entry for entry in drafts if entry.customer_id == customer.id]
        previews.append(BalancePreview(
            customer,
            previous,
            previous + sum(entry.balance_effect_paise for entry in entries),
            sum(entry.amount_paise for entry in entries if entry.type == "CREDIT"),
            sum(entry.amount_paise for entry in entries if entry.type == "PAYMENT"),
        ))
    return tuple(previews)


@router.post("/parse")
def parse_voice(payload: VoiceParseRequest, request: Request) -> VoiceParseResult:
    transcript = payload.original_transcript
    language = detect_language(transcript)
    message_language = language or TranscriptLanguage(payload.interface_language)
    try:
        with ledger_session(request.app.state.database_path) as ledger:
            actions = parse_transcript(transcript, ledger.list_customer_names(DEFAULT_SHOP_ID))
            balances = _balance_previews(ledger, actions)
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
        balances=balances,
        english_interpretation=describe_actions(actions, TranscriptLanguage.ENGLISH),
        confirmation_message=confirmation_message(actions, message_language),
    )


@router.post("/confirm")
def confirm_voice(payload: VoiceConfirmRequest, request: Request) -> TransactionBatch:
    transcript = payload.original_transcript
    language = detect_language(transcript)
    batch_id = str(payload.batch_id)
    try:
        reviewed = tuple(
            LedgerEntryDraft(action.customer_id, action.intent, action.amount_paise,
                             payment_method=action.payment_method)
            for action in payload.actions
        )
    except ValueError as error:
        raise HTTPException(422, "INVALID_REVIEW") from error

    with ledger_session(request.app.state.database_path, write=True) as ledger:
        committed = ledger.get_batch(DEFAULT_SHOP_ID, batch_id)
        if committed is not None:
            if (committed.original_transcript != transcript or committed.detected_language != language
                    or tuple(entry.as_draft() for entry in committed.entries) != reviewed):
                raise HTTPException(409, "BATCH_CONFLICT")
            return committed

        try:
            parsed = parse_transcript(transcript, ledger.list_customer_names(DEFAULT_SHOP_ID))
        except ClarificationRequired as error:
            raise HTTPException(409, "STALE_REVIEW") from error
        if _ledger_drafts(parsed) != reviewed:
            raise HTTPException(409, "STALE_REVIEW")
        current = {
            customer_id: ledger.calculate_balance(DEFAULT_SHOP_ID, customer_id)
            for customer_id in {entry.customer_id for entry in reviewed}
        }
        if current != payload.previous_balances:
            raise HTTPException(409, "STALE_REVIEW")
        return ledger.create_transaction_batch(
            DEFAULT_SHOP_ID, batch_id, reviewed,
            original_transcript=transcript, detected_language=language,
        )
