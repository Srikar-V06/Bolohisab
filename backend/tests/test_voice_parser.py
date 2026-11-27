import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.database import DEFAULT_SHOP_ID, database_transaction
from app.language_detector import TranscriptLanguage, detect_language
from app.ledger import MAX_SQLITE_INTEGER, CustomerIdentity, LedgerEntryDraft, ledger_session
from app.main import create_app
from app.number_parser import AmountError, parse_amount_paise
from app.parser import ClarificationRequired, Intent, UnresolvedAction, parse_transcript


class NumberParserTest(unittest.TestCase):
    def test_hindi_hundreds_in_both_scripts(self) -> None:
        for roman, devanagari, paise in (
            ("sau", "सौ", 10_000),
            ("dedh sau", "डेढ़ सौ", 15_000),
            ("sawa sau", "सवा सौ", 12_500),
            ("saadhe chaar sau", "साढ़े चार सौ", 45_000),
            ("paune do sau", "पौने दो सौ", 17_500),
            ("do sau pachas", "दो सौ पचास", 25_000),
        ):
            with self.subTest(roman=roman):
                self.assertEqual(parse_amount_paise(roman + " rupaye"), paise)
                self.assertEqual(parse_amount_paise(devanagari + " रुपये"), paise)

    def test_exact_decimal_and_grouped_amounts(self) -> None:
        for value, expected in (
            ("₹१,२३,४५६.७५", 12_345_675),
            ("INR 500.05", 50_005),
            ("Rs. 1,200.5", 120_050),
            ("₹0.01", 1),
            ("five hundred rupees", 50_000),
            ("92233720368547758.07", MAX_SQLITE_INTEGER),
        ):
            with self.subTest(value=value):
                self.assertEqual(parse_amount_paise(value), expected)

    def test_invalid_amounts_are_not_rounded_or_guessed(self) -> None:
        for value in (
            "500 or 600", "lagbhag sau", "do teen sau", "paune sau", "five hundred fifty-ish",
            "500.001", "1,00", "₹-500", "0", "5e2", "92233720368547758.08",
        ):
            with self.subTest(value=value), self.assertRaises(AmountError) as context:
                parse_amount_paise(value)
            self.assertFalse(context.exception.missing)
        with self.assertRaises(AmountError) as context:
            parse_amount_paise("₹")
        self.assertTrue(context.exception.missing)


class VoiceParserTest(unittest.TestCase):
    def test_language_detection(self) -> None:
        for transcript, expected in (
            ("रमेश ने 200 नकद दिए।", TranscriptLanguage.HINDI),
            ("Ramesh ka balance batao", TranscriptLanguage.HINGLISH),
            ("Record ₹५०० credit for Ramesh.", TranscriptLanguage.ENGLISH),
            ("Record ₹500 credit for रमेश.", TranscriptLanguage.ENGLISH),
            ("Diya paid ₹500.", TranscriptLanguage.ENGLISH),
            ("   ", None),
        ):
            with self.subTest(transcript=transcript):
                self.assertEqual(detect_language(transcript), expected)

    def test_optional_adapter_proposals_must_resolve_and_validate(self) -> None:
        customer = CustomerIdentity(10, "Ramesh Sharma")

        class Adapter:
            def __init__(self, amount: int) -> None:
                self.amount = amount

            def interpret(self, transcript: str) -> list[UnresolvedAction]:
                return [UnresolvedAction(Intent.CREDIT, transcript, self.amount)]

        actions = parse_transcript("रमेश शर्मा", [customer], adapter=Adapter(15_000))
        self.assertEqual(actions[0].customer, customer)
        self.assertEqual(actions[0].amount_paise, 15_000)
        with self.assertRaisesRegex(ClarificationRequired, "INVALID_AMOUNT"):
            parse_transcript("रमेश शर्मा", [customer], adapter=Adapter(-1))


class VoiceApiTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / "voice.sqlite3"
        self.client = self.enterContext(TestClient(create_app(self.path)))
        with ledger_session(self.path, write=True) as ledger:
            self.ramesh = ledger.create_customer(DEFAULT_SHOP_ID, "Ramesh")
            self.suresh = ledger.create_customer(DEFAULT_SHOP_ID, "Suresh")
            self.sita = ledger.create_customer(DEFAULT_SHOP_ID, "सीता")

    def parse(self, text: str, **preferences) -> dict:
        response = self.client.post("/api/voice/parse", json={"original_transcript": text, **preferences})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["original_transcript"], text)
        return result

    def assert_clarification(self, result: dict, code: str, index: int = 1) -> None:
        self.assertEqual(result["status"], "CLARIFICATION_REQUIRED")
        self.assertFalse(result["requires_confirmation"])
        self.assertEqual(result["actions"], [])
        self.assertEqual(result["clarification"]["code"], code)
        self.assertEqual(result["clarification"]["clause_index"], index)
        self.assertIsNone(result["english_interpretation"])
        self.assertIsNone(result["confirmation_message"])
        self.assertTrue(result["clarification_message"])

    def test_supported_credit_examples_and_exact_original_text(self) -> None:
        for text, language, localized_word in (
            ("  रमेश के खाते में ५०० रुपये उधार लिख दो। \n", "hi-IN", "उधार"),
            ("Ramesh ke khate mein 500 rupaye udhar likh do.", "hi-Latn-IN", "udhar"),
            ("Record ₹500 credit for Ramesh.", "en-IN", "credit"),
        ):
            with self.subTest(text=text):
                result = self.parse(text, interface_language="en-IN", speech_language="en-IN")
                self.assertEqual(result["detected_language"], language)
                self.assertEqual(result["status"], "REVIEW_REQUIRED")
                self.assertTrue(result["requires_confirmation"])
                self.assertEqual(result["english_interpretation"], "Record ₹500 credit for Ramesh.")
                self.assertIn(localized_word, result["confirmation_message"])
                self.assertIsNone(result["clarification_message"])
                self.assertEqual(result["actions"], [{
                    "intent": "CREDIT",
                    "customer": {"id": self.ramesh.id, "name": "Ramesh"},
                    "amount_paise": 50_000,
                    "payment_method": None,
                }])

    def test_combined_example_uses_one_customer_and_preserves_order(self) -> None:
        result = self.parse("Ramesh ke khate mein saadhe chaar sau likh do aur usne do sau cash diya hai.")
        self.assertEqual(result["detected_language"], "hi-Latn-IN")
        self.assertEqual([entry["intent"] for entry in result["actions"]], ["CREDIT", "PAYMENT"])
        self.assertEqual([entry["amount_paise"] for entry in result["actions"]], [45_000, 20_000])
        self.assertEqual([entry["payment_method"] for entry in result["actions"]], [None, "CASH"])
        self.assertEqual([entry["customer"]["id"] for entry in result["actions"]], [self.ramesh.id] * 2)
        self.assertIn("₹200 payment from Ramesh in cash", result["english_interpretation"])

    def test_payment_methods_and_balance_queries_in_supported_languages(self) -> None:
        for text, intent, name, amount, method in (
            ("Sita paid ₹200.50 via UPI.", "PAYMENT", "सीता", 20_050, "UPI"),
            ("रमेश ने 200 रुपये नकद दिए।", "PAYMENT", "Ramesh", 20_000, "CASH"),
            ("Record a payment of ₹100 for Suresh via UPI.", "PAYMENT", "Suresh", 10_000, "UPI"),
            ("Received Rs. 100 from Ramesh.", "PAYMENT", "Ramesh", 10_000, None),
            ("Ramesh ka balance batao", "BALANCE_QUERY", "Ramesh", None, None),
            ("सीता का बकाया बताइए।", "BALANCE_QUERY", "सीता", None, None),
            ("What is Suresh’s outstanding balance?", "BALANCE_QUERY", "Suresh", None, None),
        ):
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertEqual(result["status"], "REVIEW_REQUIRED", result)
                action, = result["actions"]
                self.assertEqual((action["intent"], action["customer"]["name"], action["amount_paise"], action["payment_method"]),
                                 (intent, name, amount, method))

    def test_ambiguous_prefix_reports_candidates_and_full_name_resolves(self) -> None:
        with ledger_session(self.path, write=True) as ledger:
            larger = ledger.create_customer(DEFAULT_SHOP_ID, "Ramesh Sharma")
        result = self.parse("रमेश के खाते में 500 रुपये उधार लिख दो।")
        self.assert_clarification(result, "AMBIGUOUS_CUSTOMER")
        self.assertIn("पूरा नाम", result["clarification_message"])
        self.assertEqual(result["clarification"]["candidates"], [
            {"id": self.ramesh.id, "name": "Ramesh"},
            {"id": larger.id, "name": "Ramesh Sharma"},
        ])
        full = self.parse("रमेश शर्मा के खाते में 500 रुपये उधार लिख दो।")
        self.assertEqual(full["actions"][0]["customer"], {"id": larger.id, "name": larger.name})

    def test_unknown_missing_and_uncertain_input_requests_clarification(self) -> None:
        for text, code in (
            ("रोहन के खाते में 500 रुपये उधार लिख दो।", "CUSTOMER_NOT_FOUND"),
            ("500 rupaye udhar likh do.", "MISSING_CUSTOMER"),
            ("Usne do sau cash diya.", "MISSING_CUSTOMER"),
            ("Record credit for Ramesh.", "MISSING_AMOUNT"),
            ("Ramesh paid via UPI.", "MISSING_AMOUNT"),
            ("रमेश के खाते में उधार लिख दो।", "MISSING_AMOUNT"),
            ("Ramesh ne cash diya.", "MISSING_AMOUNT"),
            ("Ramesh ne do teen sau diya.", "INVALID_AMOUNT"),
            ("Record 500 for Ramesh.", "MISSING_INTENT"),
            ("Record 500 from Ramesh.", "MISSING_INTENT"),
            ("Do not record ₹500 credit for Ramesh.", "MISSING_INTENT"),
        ):
            with self.subTest(text=text):
                self.assert_clarification(self.parse(text), code)

    def test_any_word_order_with_a_known_customer(self) -> None:
        credit, payment = ("CREDIT", None), ("PAYMENT", None)
        for text, who, paise, (intent, method) in (
            ("credit 450 to Ramesh", self.ramesh, 45000, credit),
            ("Ramesh 450 credit", self.ramesh, 45000, credit),
            ("450 credit Ramesh", self.ramesh, 45000, credit),
            ("Ramesh took 450 on credit", self.ramesh, 45000, credit),
            ("udhaar 450 Ramesh", self.ramesh, 45000, credit),
            ("Ramesh ko saadhe chaar sau udhaar", self.ramesh, 45000, credit),
            ("रमेश को 450 उधार दिया", self.ramesh, 45000, credit),
            ("Ramesh ko do sau udhaar de do", self.ramesh, 20000, credit),
            ("Ramesh 450 rupees credit", self.ramesh, 45000, credit),
            ("200 received from Ramesh", self.ramesh, 20000, payment),
            ("Ramesh 200 payment", self.ramesh, 20000, payment),
            ("got 200 from Suresh in cash", self.suresh, 20000, ("PAYMENT", "CASH")),
            ("Suresh 200 upi diya", self.suresh, 20000, ("PAYMENT", "UPI")),
        ):
            with self.subTest(text=text):
                action, = self.parse(text)["actions"]
                self.assertEqual((action["customer"]["id"], action["amount_paise"], action["intent"],
                                  action["payment_method"]), (who.id, paise, intent, method))
        both = self.parse("Ramesh 450 credit and Suresh 200 paid")["actions"]
        self.assertEqual([(a["intent"], a["amount_paise"]) for a in both], [("CREDIT", 45000), ("PAYMENT", 20000)])

    def test_word_order_fallback_never_guesses(self) -> None:
        for text, code in (
            ("Mahesh 450 credit", "CUSTOMER_NOT_FOUND"),
            ("450 credit", "MISSING_CUSTOMER"),
            ("Ramesh 450 credit 200", "MISSING_INTENT"),
            ("Ramesh sahab 450 credit", "MISSING_INTENT"),
            ("Ramesh 450", "MISSING_INTENT"),
            ("Ramesh ko 450 udhaar mat do", "MISSING_INTENT"),
        ):
            with self.subTest(text=text):
                self.assert_clarification(self.parse(text), code)

    def test_any_unclear_clause_blocks_the_entire_draft(self) -> None:
        result = self.parse("Ramesh paid ₹200 in cash and Suresh paid.")
        self.assert_clarification(result, "MISSING_AMOUNT", 2)
        result = self.parse("Ramesh paid ₹200 and record ₹100 credit.")
        self.assert_clarification(result, "MISSING_CUSTOMER", 2)
        result = self.parse("Ramesh paid ₹200 and Suresh paid ₹100 and he paid ₹50.")
        self.assert_clarification(result, "AMBIGUOUS_CUSTOMER", 3)
        result = self.parse("Ramesh paid ₹200 and Suresh paid ₹100 via UPI.")
        self.assertEqual([entry["customer"]["id"] for entry in result["actions"]], [self.ramesh.id, self.suresh.id])

    def test_database_lookup_is_scoped_and_parser_does_not_write(self) -> None:
        with database_transaction(self.path, write=True) as connection:
            connection.execute("INSERT INTO shops (id, name) VALUES (2, 'Other Shop')")
        with ledger_session(self.path, write=True) as ledger:
            ledger.create_customer(2, "Ramesh")
            opening = ledger.create_ledger_entry(
                DEFAULT_SHOP_ID, "opening", LedgerEntryDraft(self.ramesh.id, "CREDIT", 10_000),
            )

        for _ in range(2):
            result = self.parse("Record ₹500 credit for Ramesh.")
            self.assertTrue(result["requires_confirmation"])
            self.assertEqual(result["actions"][0]["customer"]["id"], self.ramesh.id)
        self.assert_clarification(self.parse("Record credit for Ramesh."), "MISSING_AMOUNT")
        with database_transaction(self.path) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM transaction_batches").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT count(*) FROM ledger_entries").fetchone()[0], 1)
        with ledger_session(self.path) as ledger:
            self.assertEqual(ledger.get_transaction_history(DEFAULT_SHOP_ID, self.ramesh.id), [opening])

    def test_missing_language_uses_interface_and_malformed_requests_are_rejected(self) -> None:
        result = self.parse("  ", interface_language="en-IN")
        self.assertIsNone(result["detected_language"])
        self.assertIn("credit", result["clarification_message"])
        alias = self.client.post("/api/voice/parse", json={"transcript": "Balance for Ramesh?"})
        self.assertEqual(alias.json()["original_transcript"], "Balance for Ramesh?")
        for body in ({}, {"original_transcript": ""}, {"original_transcript": "x" * 4097},
                     {"original_transcript": "Ramesh paid 500", "confirm": True}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/api/voice/parse", json=body).status_code, 422)
