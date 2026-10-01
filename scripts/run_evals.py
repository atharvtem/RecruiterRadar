"""Run offline RecruiterRadar evals without Tavily or live LLM calls."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from recruiterradar.models import CandidateProfile, Evidence, Match, Opportunity, Verdict
from recruiterradar.pipeline import Pipeline


DEFAULT_DATASET = ROOT / "data" / "evals" / "emscad_sample.jsonl"


SUSPICIOUS_PATTERNS = (
    r"\bwire transfer\b",
    r"\bwestern union\b",
    r"\bmoneygram\b",
    r"\bupfront\b",
    r"\bregistration fee\b",
    r"\bprocessing fee\b",
    r"\bapplication fee\b",
    r"\bdeposit\b",
    r"\bcheck\b",
    r"\bcheque\b",
    r"\bcashier'?s check\b",
    r"\bcredential",
    r"\boffice365\b",
    r"\bssn\b",
    r"\bpassport\b",
    r"\bdriver'?s license\b",
    r"\btelegram\b",
    r"\bwhatsapp\b",
    r"\b\.exe\b",
    r"\battached\b",
    r"\bpremium candidate\b",
    r"\bunlock\b.*\boffers?\b",
    r"\bunpaid training\b",
    r"\bwork from home\b",
    r"\bdata entry\b",
    r"\bno experience\b",
    r"\bimmediate start\b",
    r"\bearn \$?\d+.*per (day|week)\b",
)


@dataclass(frozen=True)
class EvalExample:
    id: str
    expected_is_fraud: bool
    expected_verdict: str
    profile: CandidateProfile
    opportunity: Opportunity
    evidence: Evidence


VERDICT_ALIASES = {
    "SPAM": "SPAM",
    "PROMOTIONAL": "PROMOTIONAL / SPONSORED",
    "PROMOTIONAL / SPONSORED": "PROMOTIONAL / SPONSORED",
    "ABSTAIN": "ABSTAIN NEEDS HUMAN",
    "ABSTAIN_NEEDS_HUMAN": "ABSTAIN NEEDS HUMAN",
    "ABSTAIN NEEDS HUMAN": "ABSTAIN NEEDS HUMAN",
    "HIGH_FIT": "HIGH FIT",
    "HIGH FIT": "HIGH FIT",
    "LOW_FIT": "LOW FIT",
    "LOW FIT": "LOW FIT",
    "SUPPORTED_FIT": "SUPPORTED_FIT",
}


class FixtureSearch:
    def __init__(self, evidence: Evidence):
        self.evidence = evidence
        self.calls = 0

    def investigate(self, opportunity: Opportunity, attempt: int) -> Evidence:
        self.calls += 1
        return self.evidence


class KeywordMatcher:
    def match(self, profile: CandidateProfile, opportunity: Opportunity, evidence: Evidence) -> Match:
        message = opportunity.message.lower()
        hits = sum(1 for skill in profile.skills if re.search(r"(?<!\w)" + re.escape(skill.lower()) + r"(?!\w)", message))
        score = min(95, 45 + hits * 15)
        return Match(score, f"Offline matcher found {hits} profile skill(s) in the posting.")


def load_examples(path: Path) -> list[EvalExample]:
    examples = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            item = json.loads(line)
            if "profile" in item and "opportunity" in item and "fixture_evidence" in item:
                profile_data = item["profile"]
                opportunity_data = item["opportunity"]
                evidence_data = item["fixture_evidence"]
                expected_verdict = item["expected_verdict"]
                expected_is_fraud = bool(item["expected_is_fraud"])
            else:
                expected_verdict = normalize_expected(item["expected_verdict"])
                expected_is_fraud = expected_verdict == Verdict.SPAM.value
                profile_data = profile_from_resume(item.get("resume", ""))
                opportunity_data = {
                    "message": item["message"],
                    "sender_email": item.get("sender_email", ""),
                    "company": item.get("company", ""),
                }
                evidence_data = fixture_evidence_for(expected_verdict, item.get("expected_assessment", ""))
            examples.append(
                EvalExample(
                    id=item.get("id") or f"line_{line_number}",
                    expected_is_fraud=expected_is_fraud,
                    expected_verdict=expected_verdict,
                    profile=CandidateProfile(tuple(profile_data["skills"]), profile_data.get("experience", "")),
                    opportunity=Opportunity(
                        opportunity_data["message"],
                        sender_email=opportunity_data.get("sender_email", ""),
                        company=opportunity_data.get("company", ""),
                    ),
                    evidence=Evidence(
                        bool(evidence_data["verified"]),
                        evidence_data["reason"],
                        tuple(evidence_data.get("sources", ())),
                        bool(evidence_data.get("opportunity_supported", False)),
                        evidence_data.get("classification", "unverified"),
                    ),
                )
            )
    return examples


def normalize_expected(value: str) -> str:
    normalized = str(value).strip().upper().replace("-", "_")
    normalized = re.sub(r"\s+", " ", normalized.replace("_", " "))
    key = normalized.replace(" ", "_")
    if key in VERDICT_ALIASES:
        return VERDICT_ALIASES[key]
    if normalized in VERDICT_ALIASES:
        return VERDICT_ALIASES[normalized]
    raise ValueError(f"Unsupported expected_verdict: {value!r}")


def profile_from_resume(resume: str) -> dict[str, object]:
    parts = [part.strip() for part in re.split(r"[,;/|]", resume) if part.strip()]
    skills = tuple(dict.fromkeys(parts or ["communication"]))
    return {"skills": list(skills), "experience": resume}


def fixture_evidence_for(expected_verdict: str, assessment: str) -> dict[str, object]:
    if expected_verdict == Verdict.SPAM.value:
        return {
            "verified": False,
            "reason": f"Eval fixture marks this recruiter message as suspicious: {assessment}.",
            "sources": [],
            "opportunity_supported": False,
            "classification": "suspicious",
        }
    if expected_verdict == Verdict.PROMOTIONAL.value:
        return {
            "verified": False,
            "reason": f"Eval fixture marks this recruiter message as promotional: {assessment}.",
            "sources": [],
            "opportunity_supported": False,
            "classification": "promotional",
        }
    if expected_verdict == Verdict.ABSTAIN.value:
        return {
            "verified": False,
            "reason": f"Eval fixture marks this recruiter message as unverified: {assessment}.",
            "sources": [],
            "opportunity_supported": False,
            "classification": "unverified",
        }
    return {
        "verified": True,
        "reason": f"Eval fixture marks this recruiter message as supported: {assessment}.",
        "sources": ["https://example.com/offline-recruiter-fixture"],
        "opportunity_supported": True,
        "classification": "supported",
    }


def expected_matches(expected: str, verdict: Verdict) -> bool:
    if expected == "SUPPORTED_FIT":
        return verdict in {Verdict.HIGH_FIT, Verdict.LOW_FIT}
    return verdict.value == normalize_expected(expected)


def heuristic_predicts_fraud(example: EvalExample) -> bool:
    text = example.opportunity.message.lower()
    if any(re.search(pattern, text, re.I) for pattern in SUSPICIOUS_PATTERNS):
        return True
    if "has_company_logo: f" in text and "has_questions: f" in text:
        return True
    return False


def percent(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{(100 * numerator / denominator):.1f}%"


def run_pipeline_fixture_eval(examples: list[EvalExample]) -> dict[str, object]:
    started = time.monotonic()
    counts = Counter()
    failures = []
    for example in examples:
        search = FixtureSearch(example.evidence)
        result = Pipeline(search, KeywordMatcher()).run(example.profile, example.opportunity)
        counts[result.verdict.value] += 1
        if not expected_matches(example.expected_verdict, result.verdict):
            failures.append(
                {
                    "id": example.id,
                    "expected": example.expected_verdict,
                    "actual": result.verdict.value,
                    "reason": result.reason[:240],
                }
            )
    passed = len(examples) - len(failures)
    return {
        "name": "pipeline_fixture",
        "total": len(examples),
        "passed": passed,
        "failed": len(failures),
        "accuracy": percent(passed, len(examples)),
        "seconds": round(time.monotonic() - started, 3),
        "verdicts": dict(counts),
        "failures": failures,
    }


def run_heuristic_baseline(examples: list[EvalExample]) -> dict[str, object]:
    started = time.monotonic()
    tp = fp = tn = fn = 0
    failures = []
    for example in examples:
        predicted = heuristic_predicts_fraud(example)
        actual = example.expected_is_fraud
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
            failures.append({"id": example.id, "expected": "real", "actual": "fraud"})
        elif not predicted and actual:
            fn += 1
            failures.append({"id": example.id, "expected": "fraud", "actual": "real"})
        else:
            tn += 1
    return {
        "name": "keyword_fraud_baseline",
        "total": len(examples),
        "accuracy": percent(tp + tn, len(examples)),
        "fraud_recall": percent(tp, tp + fn),
        "fraud_precision": percent(tp, tp + fp),
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "seconds": round(time.monotonic() - started, 3),
        "failures": failures,
    }


def print_report(result: dict[str, object], max_failures: int) -> None:
    print(f"\n== {result['name']} ==")
    for key, value in result.items():
        if key == "failures":
            continue
        print(f"{key}: {value}")
    failures = result.get("failures", [])
    if failures:
        print(f"sample_failures ({min(max_failures, len(failures))}/{len(failures)}):")
        for failure in failures[:max_failures]:
            print(json.dumps(failure, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--max-failures", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    examples = load_examples(args.dataset)
    results = [run_pipeline_fixture_eval(examples), run_heuristic_baseline(examples)]

    if args.json:
        print(json.dumps({"dataset": str(args.dataset), "results": results}, indent=2, ensure_ascii=False))
    else:
        print(f"Dataset: {args.dataset}")
        print(f"Examples: {len(examples)}")
        print("Network/API usage: none")
        for result in results:
            print_report(result, args.max_failures)

    return 1 if results[0]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
