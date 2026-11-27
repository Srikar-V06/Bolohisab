import unittest

from pydantic import ValidationError

from app.localization import LanguagePreferences, VoiceTranscriptRequest


class LocalizationTest(unittest.TestCase):
    def test_language_preferences_default_to_hindi(self) -> None:
        self.assertEqual(
            LanguagePreferences().model_dump(mode="json"),
            {"interface_language": "hi-IN", "speech_language": "hi-IN"},
        )

    def test_transcript_and_independent_language_preferences_round_trip(self) -> None:
        payload = {
            "interface_language": "en-IN",
            "speech_language": "hi-IN",
            "original_transcript": "  Priya Sharma ने ₹1,234.50 दिए। BH-001 01/02/2026 \n",
        }
        request = VoiceTranscriptRequest.model_validate(payload)
        self.assertEqual(request.model_dump(mode="json"), payload)

    def test_schema_rejects_unsupported_language_and_empty_transcript(self) -> None:
        with self.assertRaises(ValidationError):
            LanguagePreferences(interface_language="fr-FR")
        with self.assertRaises(ValidationError):
            VoiceTranscriptRequest(original_transcript="")
