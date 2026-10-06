"""Offline UI checks: no OAuth, Firestore, or provider requests."""
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from recruiterradar.firebase import FirebaseUser, FirebaseUnavailable, is_developer
from recruiterradar.providers.live import Settings


class AppTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(firebase_project_id="test", firebase_web_api_key="test",
                                 google_client_id="test", google_client_secret="test",
                                 google_redirect_uri="http://localhost:8517",
                                 developer_uids=("developer",))

    def run_app(self, uid=None, failure=None):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
        if uid:
            app.session_state["firebase_user"] = FirebaseUser(uid, "tester@example.com", "test")
        with patch("recruiterradar.providers.live.Settings.load", return_value=self.settings), \
             patch("recruiterradar.firebase.usage", return_value={"searches": 2}, side_effect=failure) as usage:
            app.run()
        self.assertFalse(app.exception)
        return app, usage

    def test_login_has_no_debug_or_workspace(self):
        app, usage = self.run_app()
        self.assertEqual(app.title[0].value, "RecruiterRadar")
        self.assertEqual(len(app.text_input), 0)
        self.assertFalse(any(x.label == "OAuth debug" for x in app.expander))
        usage.assert_not_called()

    def test_regular_user_keeps_quota(self):
        app, usage = self.run_app("regular")
        usage.assert_called_once()
        self.assertEqual(app.metric[0].value, "3 / 5")
        self.assertFalse(any(x.label == "Developer diagnostics" for x in app.expander))

    def test_developer_skips_firestore_quota(self):
        app, usage = self.run_app("developer")
        usage.assert_not_called()
        self.assertEqual(app.metric[0].value, "Developer")

    def test_usage_failure_blocks_workspace(self):
        app, _ = self.run_app("regular", FirebaseUnavailable("denied", status="PERMISSION_DENIED"))
        self.assertEqual(len(app.error), 1)
        self.assertEqual(len(app.text_input), 0)

    def test_developer_requires_exact_authenticated_uid(self):
        self.assertFalse(is_developer(self.settings, None))
        self.assertFalse(is_developer(self.settings, FirebaseUser("dev", "developer", "test")))

    def test_clear_keeps_login(self):
        app, _ = self.run_app("developer")
        with patch("recruiterradar.providers.live.Settings.load", return_value=self.settings):
            next(b for b in app.button if b.label == "Clear workspace").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["firebase_user"].uid, "developer")
