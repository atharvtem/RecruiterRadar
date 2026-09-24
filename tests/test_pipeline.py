import socket
import unittest
from unittest.mock import patch

from recruiterradar.models import CandidateProfile, Evidence, Opportunity, Verdict
from recruiterradar.pipeline import Pipeline
from recruiterradar.providers.demo import DemoMatcher, DemoSearch
from recruiterradar.resume import extract_resume


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.network_guard = patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden in offline tests"))
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)
        self.profile = CandidateProfile(("Python", "SQL"))

    def test_spam_short_circuits_providers(self):
        class NeverSearch:
            def investigate(self, *args):
                raise AssertionError("Spam must not reach search")
        result = Pipeline(NeverSearch()).run(self.profile, Opportunity("Pay an upfront fee", company="Any"))
        self.assertEqual(result.verdict, Verdict.SPAM)
        self.assertEqual(result.search_attempts, 0)

    def test_default_providers_abstain_without_network(self):
        result = Pipeline().run(self.profile, Opportunity("Python role", company="Some Company"))
        self.assertEqual(result.verdict, Verdict.ABSTAIN)
        self.assertIn("disabled", result.reason)

    def test_missing_company_abstains_without_search(self):
        result = Pipeline().run(self.profile, Opportunity("Confidential role"))
        self.assertEqual(result.search_attempts, 0)
        self.assertEqual(result.verdict, Verdict.ABSTAIN)

    def test_retries_are_bounded(self):
        class Search:
            def __init__(self): self.attempts = []
            def investigate(self, opportunity, attempt):
                self.attempts.append(attempt)
                return Evidence(False, "No evidence", retry_worthwhile=True)
        search = Search()
        result = Pipeline(search).run(self.profile, Opportunity("Python role", company="Stealth"))
        self.assertEqual(search.attempts, [1, 2, 3])
        self.assertEqual(result.verdict, Verdict.ABSTAIN)

    def test_verification_requires_sources(self):
        class Search:
            def investigate(self, *args): return Evidence(True, "Unsupported claim")
        result = Pipeline(Search()).run(self.profile, Opportunity("Python role", company="Unknown"))
        self.assertEqual(result.verdict, Verdict.ABSTAIN)

    def test_company_existence_never_implies_offer_support(self):
        from unittest.mock import Mock
        search = Mock()
        search.investigate.return_value = Evidence(True, "Company exists", ("https://example.com",))
        matcher = Mock()
        result = Pipeline(search, matcher).run(self.profile, Opportunity("An offer", company="Example"))
        self.assertEqual(result.verdict, Verdict.ABSTAIN)
        self.assertIsNone(result.score)
        self.assertEqual(result.search_attempts, 1)
        matcher.match.assert_not_called()

    def test_risk_and_promotion_stop_before_fit(self):
        from unittest.mock import Mock
        for classification, verdict in (("suspicious", Verdict.SPAM), ("promotional", Verdict.PROMOTIONAL), ("stealth", Verdict.ABSTAIN)):
            with self.subTest(classification=classification):
                search, matcher = Mock(), Mock()
                search.investigate.return_value = Evidence(True, "Assessment", ("https://example.com",), classification=classification)
                result = Pipeline(search, matcher).run(self.profile, Opportunity("Outreach", company="Example"))
                self.assertEqual(result.verdict, verdict)
                self.assertEqual(result.search_attempts, 1)
                matcher.match.assert_not_called()

    def test_profiles_do_not_leak_between_runs(self):
        pipeline = Pipeline(DemoSearch(), DemoMatcher(), simulated=True)
        opportunity = Opportunity("Python SQL", company="Example Robotics")
        first = pipeline.run(self.profile, opportunity)
        second = pipeline.run(CandidateProfile(("Nursing",)), opportunity)
        self.assertEqual(first.verdict, Verdict.HIGH_FIT)
        self.assertEqual(second.verdict, Verdict.LOW_FIT)
        self.assertTrue(first.simulated)

    def test_domain_exclusions_respect_boundaries(self):
        profile = CandidateProfile(("Python",), excluded_domains=("blocked.example",))
        for sender in ("x@blocked.example", "x@sub.blocked.example"):
            self.assertEqual(Pipeline().run(profile, Opportunity("Role", sender)).verdict, Verdict.SPAM)
        self.assertEqual(Pipeline().run(profile, Opportunity("Role", "x@notblocked.example")).verdict, Verdict.ABSTAIN)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError): Opportunity(" ")
        with self.assertRaises(ValueError): Opportunity("x" * 20_001)
        with self.assertRaises(ValueError): extract_resume(b"not a pdf")
        with self.assertRaises(ValueError): extract_resume(b"%PDF-" + b"x" * (5 * 1024 * 1024))


if __name__ == "__main__":
    unittest.main()
