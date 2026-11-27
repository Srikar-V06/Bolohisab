import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.database import DEFAULT_SHOP_ID
from app.ledger import CustomerIdentity, ledger_session
from app.local_model import LocalModelAdapter
from app.main import create_app
from app.parser import ClarificationRequired, Intent, PaymentMethod, parse_transcript


class StubModel(LocalModelAdapter):
    """Returns fixed proposals instead of calling Ollama, and counts calls."""

    def __init__(self, *proposals: dict, fail: bool = False) -> None:
        super().__init__("stub")
        self.proposals, self.fail, self.calls = list(proposals), fail, 0

    def warm(self) -> None:
        pass

    def _ask(self, transcript: str) -> list[dict]:
        self.calls += 1
        if self.fail:
            raise OSError("connection refused")
        return self.proposals


def act(intent: str, customer: str | None, amount: str | None, method: str | None = None) -> dict:
    return {"intent": intent, "customer_words": customer, "amount_words": amount, "method_words": method}


RAMESH = CustomerIdentity(1, "Ramesh Kumar")
SUNITA = CustomerIdentity(2, "Sunita Devi")
PEOPLE = [RAMESH, SUNITA]


class LocalModelTest(unittest.TestCase):
    def test_rules_win_and_the_model_is_not_called(self) -> None:
        model = StubModel(act("PAYMENT", "Ramesh", "999"))
        action, = parse_transcript("Ramesh 450 credit", PEOPLE, fallback=model)
        self.assertEqual((action.intent, action.amount_paise), (Intent.CREDIT, 45000))
        self.assertEqual(model.calls, 0)

    def test_model_reads_free_speech_and_the_app_parses_the_amount(self) -> None:
        text = "Ramesh bhaiya ne kal wale 500 mein se 200 de diye cash mein"
        action, = parse_transcript(text, PEOPLE, fallback=StubModel(act("PAYMENT", "Ramesh bhaiya", "200", "cash")))
        self.assertEqual((action.intent, action.customer, action.amount_paise, action.payment_method),
                         (Intent.PAYMENT, RAMESH, 20000, PaymentMethod.CASH))
        hindi = "रमेश को साढ़े चार सौ का सामान उधार में दे दिया था"
        action, = parse_transcript(hindi, PEOPLE, fallback=StubModel(act("CREDIT", "रमेश", "साढ़े चार सौ")))
        self.assertEqual((action.customer, action.amount_paise), (RAMESH, 45000))

    def test_words_the_shopkeeper_did_not_say_are_rejected(self) -> None:
        text = "Ramesh bhaiya ne kal wale paise de diye"
        for proposal in (act("PAYMENT", "Ramesh", "500"),            # amount never said
                         act("PAYMENT", "Mahesh", None),             # name never said
                         act("PAYMENT", "Ramesh", None, "UPI")):     # method never said
            with self.subTest(proposal=proposal), self.assertRaises(ClarificationRequired):
                parse_transcript(text, PEOPLE, fallback=StubModel(proposal))

    def test_unclear_amount_and_unknown_customer_still_ask_again(self) -> None:
        with self.assertRaisesRegex(ClarificationRequired, "INVALID_AMOUNT|MISSING_INTENT"):
            parse_transcript("Ramesh ko do teen sau ka maal de do", PEOPLE,
                             fallback=StubModel(act("CREDIT", "Ramesh", "do teen sau")))
        with self.assertRaisesRegex(ClarificationRequired, "CUSTOMER_NOT_FOUND"):
            parse_transcript("Mohan ko 50 ka saamaan diya hai yaar", PEOPLE,
                             fallback=StubModel(act("CREDIT", "Mohan", "50")))

    def test_model_down_falls_back_to_the_rules_answer(self) -> None:
        with self.assertRaisesRegex(ClarificationRequired, "MISSING_INTENT"):
            parse_transcript("Ramesh ka kuch hisaab karna tha", PEOPLE, fallback=StubModel(fail=True))

    def test_review_and_confirm_use_the_same_reading(self) -> None:
        model = StubModel(act("CREDIT", "Sunita", "300"))
        with TemporaryDirectory() as folder, TestClient(create_app(Path(folder) / "db.sqlite3", model)) as client:
            with ledger_session(Path(folder) / "db.sqlite3", write=True) as ledger:
                ledger.create_customer(DEFAULT_SHOP_ID, "Sunita Devi")
            text = "Sunita didi ka 300 wala maal khate mein chadha do"
            preview = client.post("/api/voice/parse", json={"transcript": text, "interface_language": "en-IN"}).json()
            self.assertEqual(preview["status"], "REVIEW_REQUIRED")
            saved = client.post("/api/voice/confirm", json={
                "transcript": text, "interface_language": "en-IN",
                "batch_id": "3f0e8d36-1f5e-4c55-9d1e-6d0a6f2f6a10",
                "actions": [{"customer_id": a["customer"]["id"], "intent": a["intent"], "amount_paise": a["amount_paise"]}
                            for a in preview["actions"]],
                "previous_balances": {str(b["customer"]["id"]): b["previous_balance_paise"] for b in preview["balances"]},
            })
            self.assertEqual(saved.status_code, 200, saved.text)
            self.assertEqual(model.calls, 1)


if __name__ == "__main__":
    unittest.main()
