import json
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from recruiterradar import firebase
from recruiterradar.providers.live import Settings


class FirebaseTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(firebase_project_id="project", firebase_web_api_key="web-key")
        self.user = firebase.FirebaseUser("uid123", "a@example.com", "id-token")

    def test_month_key_uses_utc_month(self):
        self.assertEqual(firebase.month_key(datetime(2026, 10, 1, tzinfo=timezone.utc)), "2026-10")

    def test_sign_in_uses_identity_toolkit_and_returns_user(self):
        response = {
            "localId": "uid123", "email": "a@example.com",
            "idToken": "id-token", "refreshToken": "refresh",
        }
        with patch("recruiterradar.firebase.urlopen", return_value=Mock(__enter__=lambda s: s, __exit__=lambda *a: None, read=lambda: json.dumps(response).encode())) as opener:
            user = firebase.sign_in(self.settings, "a@example.com", "pw")
        request = opener.call_args.args[0]
        self.assertIn("accounts:signInWithPassword", request.full_url)
        self.assertEqual(user.uid, "uid123")
        self.assertEqual(user.id_token, "id-token")

    def test_missing_usage_document_counts_as_zero(self):
        body = json.dumps({"error": {"message": "NOT_FOUND"}}).encode()
        with patch("recruiterradar.firebase.urlopen", side_effect=HTTPError("url", 404, "missing", {}, Mock(read=lambda: body))):
            self.assertEqual(firebase.usage(self.settings, self.user, "2026-10")["searches"], 0)

    def test_set_usage_patches_firestore_document(self):
        response = {"fields": {"uid": {"stringValue": "uid123"}, "month": {"stringValue": "2026-10"}, "searches": {"integerValue": "4"}}}
        with patch("recruiterradar.firebase.urlopen", return_value=Mock(__enter__=lambda s: s, __exit__=lambda *a: None, read=lambda: json.dumps(response).encode())) as opener:
            result = firebase.set_usage(self.settings, self.user, 4, "2026-10")
        request = opener.call_args.args[0]
        self.assertEqual(request.get_method(), "PATCH")
        self.assertEqual(request.get_header("Authorization"), "Bearer id-token")
        self.assertEqual(result["searches"], 4)


if __name__ == "__main__":
    unittest.main()
