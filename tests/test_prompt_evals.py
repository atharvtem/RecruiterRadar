import unittest
from unittest.mock import Mock

from recruiterradar.models import Opportunity
from recruiterradar.providers.live import LiveSearch, Settings
from scripts.run_prompt_evals import comparison, metrics, model_input


class PromptEvalTests(unittest.TestCase):
    def test_fixed_evidence_never_searches_and_critic_sees_draft(self):
        draft = {"verified": True, "opportunity_supported": True,
                 "classification": "supported", "reason": "Role", "sources": ["https://firm.example/jobs"]}
        revised = {**draft, "classification": "unverified", "opportunity_supported": False,
                   "reason": "Affiliation not established"}
        llm = Mock()
        llm.json.side_effect = [draft, revised]
        transport = Mock(side_effect=AssertionError("Retrieval forbidden"))
        search = LiveSearch(Settings(), llm, transport, prompt_variant="critic")
        evidence = search.assess_documents(Opportunity("Role", "hr@firm.example", "Firm"),
                                          [{"url": "https://firm.example/jobs", "content": "Role", "title": "Jobs"}])
        transport.assert_not_called()
        self.assertEqual(llm.json.call_count, 2)
        self.assertEqual(llm.json.call_args.args[1]["draft_assessment"], draft)
        self.assertFalse(evidence.opportunity_supported)

    def test_labels_and_ids_are_excluded(self):
        case = {"id": "spam_secret", "expected_verdict": "SPAM", "target": "suspicious",
                "expected_assessment": "secret", "message": "Hello", "sender_email": "a@b.example", "company": "B"}
        self.assertEqual(vars(model_input(case)), {"message": "Hello", "sender_email": "a@b.example", "company": "B"})

    def test_metrics_count_abstention_as_missed_fraud_and_errors_separately(self):
        rows = [{"target": "suspicious", "prediction": "abstain"},
                {"target": "suspicious", "prediction": "suspicious"},
                {"target": "supported", "prediction": "suspicious"},
                {"target": "supported", "prediction": "supported"},
                {"target": "abstain", "prediction": "supported"},
                {"target": "suspicious", "error": "quota"}]
        result = metrics(rows)
        self.assertEqual(result["fraud_recall"], 0.5)
        self.assertEqual(result["false_positives"], 1)
        self.assertEqual(result["abstain_rate"], 0.2)
        self.assertEqual(result["supported_opportunity_precision"], 0.5)
        self.assertEqual(result["errors"], 1)
        self.assertIsNone(metrics([])["supported_opportunity_precision"])

    def test_comparison_reports_regressions(self):
        rows = [{"id": "a", "variant": "few_shot", "target": "supported", "prediction": "supported"},
                {"id": "a", "variant": "critic", "target": "supported", "prediction": "abstain"}]
        self.assertEqual(comparison(rows)["few_shot_to_critic"]["regressed"], ["a"])


if __name__ == "__main__":
    unittest.main()
