import json
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from recruiterradar import firebase
from recruiterradar.providers.live import Settings


class FirebaseTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(firebase_project_id="project", firebase_web_api_key="web-key",
                                 google_client_id="client-id", google_client_secret="client-secret",
                                 google_redirect_uri="http://localhost:8501")
        self.user = firebase.FirebaseUser("uid123", "a@example.com", "id-token")

    def test_month_key_uses_utc_month(self):
        self.assertEqual(firebase.month_key(datetime(2026, 10, 1, tzinfo=timezone.utc)), "2026-10")

    def test_google_auth_url_contains_oauth_params(self):
        url = firebase.google_auth_url(self.settings, "state-123")
        self.assertIn("accounts.google.com", url)
        self.assertIn("client_id=client-id", url)
        self.assertIn("state=state-123", url)

    def test_oauth_state_is_signed_and_time_limited(self):
        state = firebase.oauth_state(self.settings, now=1000)
        self.assertTrue(firebase.verify_oauth_state(self.settings, state, now=1005))
        self.assertFalse(firebase.verify_oauth_state(self.settings, state + "x", now=1005))
        self.assertFalse(firebase.verify_oauth_state(self.settings, state, now=2000))

    def test_google_code_exchange_returns_firebase_user(self):
        responses = [
            {"id_token": "google-id-token"},
            {"localId": "uid123", "email": "a@example.com", "idToken": "firebase-id-token", "refreshToken": "refresh"},
        ]
        with patch("recruiterradar.firebase.urlopen", side_effect=[
            Mock(__enter__=lambda s: s, __exit__=lambda *a: None, read=lambda r=response: json.dumps(r).encode())
            for response in responses
        ]) as opener:
            user = firebase.sign_in_with_google_code(self.settings, "code-123")
        token_request = opener.call_args_list[0].args[0]
        firebase_request = opener.call_args_list[1].args[0]
        self.assertIn("oauth2.googleapis.com/token", token_request.full_url)
        self.assertIn("accounts:signInWithIdp", firebase_request.full_url)
        self.assertIn("providerId=google.com", json.loads(firebase_request.data)["postBody"])
        request = opener.call_args.args[0]
        self.assertIn("accounts:signInWithIdp", request.full_url)
        self.assertEqual(user.uid, "uid123")
        self.assertEqual(user.id_token, "firebase-id-token")

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
