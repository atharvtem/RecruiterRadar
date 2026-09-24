"""Live adapter contracts tested with fake responses and outbound sockets blocked."""
import io
import json
import socket
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from recruiterradar.models import CandidateProfile, Evidence, Opportunity, Verdict
from recruiterradar.pipeline import Pipeline
from recruiterradar.providers.base import ProviderUnavailable
from recruiterradar.providers.live import LiveLLM, LiveSearch, RequestFailure, Settings, post_json, publish_metrics


def completion(data):
    return {"choices": [{"message": {"content": json.dumps(data)}}], "usage": {"total_tokens": 12}}


class LiveTests(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.getaddrinfo"):
            guard = patch(target, side_effect=AssertionError("Outbound network forbidden"))
            guard.start()
            self.addCleanup(guard.stop)
        self.settings = Settings(groq_key="fake", google_key="fake", tavily_key="fake")

    def test_profile_and_usage(self):
        transport = Mock(return_value=completion({"skills": ["Python", "Python"], "experience": "Built APIs"}))
        llm = LiveLLM(self.settings, transport)
        self.assertEqual(llm.profile("resume").skills, ("Python",))
        self.assertEqual(llm.metrics[0]["tokens"], 12)

    def test_groq_failure_uses_gemini_when_configured(self):
        for status in (401, 403, 404, 429, None):
            with self.subTest(status=status):
                transport = Mock(side_effect=[RequestFailure("Groq", status), {
                    "candidates": [{"content": {"parts": [{"text": '{"skills":["SQL"],"experience":"Analyst"}'}]}}],
                    "usageMetadata": {"totalTokenCount": 20},
                }])
                llm = LiveLLM(self.settings, transport)
                self.assertEqual(llm.profile("resume").skills, ("SQL",))
                self.assertTrue(transport.call_args.kwargs["google"])
                self.assertEqual(llm.metrics[0]["provider"], "gemini")

    def test_groq_failure_without_gemini_keeps_groq_error(self):
        transport = Mock(side_effect=[RequestFailure("Groq", 403)])
        with self.assertRaisesRegex(ProviderUnavailable, "Groq request failed"):
            LiveLLM(Settings(groq_key="fake"), transport).profile("resume")
        self.assertEqual(transport.call_count, 1)

    def test_fallback_error_mentions_both_providers(self):
        transport = Mock(side_effect=[RequestFailure("Groq", 403), RequestFailure("Gemini", 503)])
        with self.assertRaisesRegex(ProviderUnavailable, "Groq request failed.*Fallback also failed.*Gemini request failed"):
            LiveLLM(self.settings, transport).profile("resume")
        self.assertEqual(transport.call_count, 2)

    def test_invalid_outputs_are_controlled(self):
        for response in ({}, completion([]), completion({"skills": "Python"}), completion({"skills": ["SQL"], "experience": None})):
            with self.subTest(response=response), self.assertRaises(ProviderUnavailable):
                LiveLLM(self.settings, Mock(return_value=response)).profile("resume")
        for score in (True, "90", 101, -1):
            with self.subTest(score=score), self.assertRaises(ProviderUnavailable):
                LiveLLM(self.settings, Mock(return_value=completion({"score": score, "reason": "Fit"}))).match(CandidateProfile(("SQL",)), Opportunity("role"), Evidence(True, "reason"))

    def test_query_rewrite_and_citation_filter(self):
        llm = Mock()
        llm.json.side_effect = [
            {"verified": False, "reason": "Ambiguous identity", "sources": [], "next_query": "Example Robotics official engineering team", "retry_worthwhile": True},
            {"verified": True, "reason": "Product evidence", "sources": ["https://invented.example", "https://example.com/team"]},
        ]
        transport = Mock(return_value={"results": [{"url": "https://example.com/team", "content": "Robotics engineering team"}]})
        search = LiveSearch(self.settings, llm, transport)
        opportunity = Opportunity("role", company="Example Robotics")
        self.assertFalse(search.investigate(opportunity, 1).verified)
        evidence = search.investigate(opportunity, 2)
        self.assertEqual(evidence.sources, ("https://example.com/team",))
        self.assertEqual(transport.call_args.args[3]["query"], "Example Robotics official engineering team")

    def test_invented_sources_do_not_verify(self):
        llm = Mock()
        llm.json.return_value = {"verified": True, "reason": "Unsupported", "sources": ["https://invented.example"]}
        search = LiveSearch(self.settings, llm, Mock(return_value={"results": []}))
        self.assertFalse(search.investigate(Opportunity("role", company="Unknown"), 1).verified)

    def test_company_only_response_cannot_unlock_fit(self):
        llm = Mock()
        llm.json.return_value = {"verified": True, "reason": "Company exists", "sources": ["https://example.com"]}
        search = LiveSearch(self.settings, llm, Mock(return_value={"results": [{"url": "https://example.com", "content": "Company website"}]}))
        evidence = search.investigate(Opportunity("An offer", company="Example"), 1)
        self.assertTrue(evidence.verified)
        self.assertFalse(evidence.opportunity_supported)
        self.assertEqual(llm.json.call_args.args[1]["message"], "An offer")

    def test_repeated_query_stops_and_evidence_accumulates(self):
        llm = Mock()
        llm.json.return_value = {"verified": False, "reason": "Missing affiliation", "sources": [], "retry_worthwhile": True, "next_query": "Example official recruiter affiliation"}
        transport = Mock(side_effect=[{"results": [{"url": "https://example.com", "content": "Company"}]}, {"results": []}])
        search = LiveSearch(self.settings, llm, transport)
        opportunity = Opportunity("Role", company="Example")
        self.assertTrue(search.investigate(opportunity, 1).retry_worthwhile)
        self.assertFalse(search.investigate(opportunity, 2).retry_worthwhile)
        self.assertEqual(len(llm.json.call_args.args[1]["documents"]), 1)

    def test_transport_missing_key_never_opens_socket(self):
        with patch("recruiterradar.providers.live.urlopen") as opener:
            with self.assertRaisesRegex(ProviderUnavailable, "missing"):
                post_json("Groq", "https://api.groq.com", "", {})
            opener.assert_not_called()

    def test_transport_errors_redact_credentials_and_body(self):
        for error in (HTTPError("https://api.groq.com", 401, "secret", {}, None), URLError("secret"), TimeoutError("secret")):
            with patch("recruiterradar.providers.live.urlopen", side_effect=error):
                with self.assertRaises(ProviderUnavailable) as caught:
                    post_json("Groq", "https://api.groq.com", "secret", {})
                self.assertNotIn("secret", str(caught.exception))

    def test_transport_headers_and_json(self):
        with patch("recruiterradar.providers.live.urlopen", return_value=io.BytesIO(b'{"ok":true}')) as opener:
            self.assertEqual(post_json("Gemini", "https://example.com", "fake", {"a": 1}, google=True), {"ok": True})
            request = opener.call_args.args[0]
            self.assertEqual(request.get_header("X-goog-api-key"), "fake")
            self.assertEqual(json.loads(request.data), {"a": 1})

    def test_graph_live_adapters_with_mock_transport(self):
        from langsmith import tracing_context
        llm = LiveLLM(self.settings, Mock(side_effect=[
            completion({"opportunity_supported": True, "classification": "supported", "verified": True, "reason": "Engineering team and product documented; funding unknown", "sources": ["https://example.com"]}),
            completion({"score": 85, "reason": "Python aligns with requirements"}),
        ]))
        search = LiveSearch(self.settings, llm, Mock(return_value={"results": [{"url": "https://example.com", "content": "Engineering product"}]}))
        with tracing_context(enabled=False):
            state = Pipeline(search, llm).compile_graph().invoke({"profile": CandidateProfile(("Python",)), "opportunity": Opportunity("Python role", sender_email="hr@example.com", company="Example"), "attempts": 0})
        self.assertEqual(state["result"].verdict, Verdict.HIGH_FIT)
        self.assertFalse(state["result"].simulated)

    def test_tracing_off_is_inert(self):
        publish_metrics(self.settings, "test", [], "ready")

    def test_ui_parse_evaluate_rerun_and_clear_without_requests(self):
        from streamlit.testing.v1 import AppTest
        upload = Mock()
        upload.getvalue.return_value = b"%PDF-fake"
        with patch("streamlit.file_uploader", return_value=upload), patch("recruiterradar.resume.extract_resume", return_value="Python developer"), patch.object(Settings, "load", return_value=self.settings), patch.object(LiveLLM, "json") as llm, patch("recruiterradar.providers.live.urlopen", return_value=io.BytesIO(b'{"results":[{"url":"https://example.com","content":"Product team"}]}')) as opener:
            llm.side_effect = [
                {"skills": ["Python"], "experience": "Developer"},
                {"opportunity_supported": True, "classification": "supported", "verified": True, "reason": "Product evidence", "sources": ["https://example.com"]},
                {"score": 80, "reason": "Python experience matches"},
            ]
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
            self.assertFalse(app.exception)
            self.assertEqual(llm.call_count, 0)
            opener.assert_not_called()
            app.button[1].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(llm.call_count, 1)
            app.text_input[0].set_value("Example")
            app.text_input[1].set_value("hr@example.com")
            app.text_area[0].set_value("Python role")
            app.button[2].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.subheader[0].value, "HIGH FIT")
            app.run()
            self.assertEqual(llm.call_count, 3)
            self.assertEqual(opener.call_count, 1)
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertNotIn("candidate_profile", app.session_state)
            self.assertNotIn("result", app.session_state)


if __name__ == "__main__":
    unittest.main()
