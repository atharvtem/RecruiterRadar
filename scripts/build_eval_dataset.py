"""Build a small offline eval set from the EMSCAD-style raw CSV.

The raw dataset stays in data/raw and can be large. This script creates a
balanced JSONL sample that is safe to commit and fast to run in local evals.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import random
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "raw" / "DataSet.csv"
DEFAULT_OUTPUT = ROOT / "data" / "evals" / "emscad_sample.jsonl"


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def clean(value: str | None) -> str:
    text = html.unescape(value or "")
    text = TAG_RE.sub(" ", text)
    return SPACE_RE.sub(" ", text).strip()


def label_is_fraud(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "t", "yes", "y", "fraudulent"}


def make_message(row: dict[str, str]) -> str:
    parts = [
        ("Title", row.get("title")),
        ("Location", row.get("location")),
        ("Employment type", row.get("employment_type")),
        ("Experience", row.get("required_experience")),
        ("Education", row.get("required_education")),
        ("Industry", row.get("industry")),
        ("Function", row.get("function")),
        ("Salary", row.get("salary_range")),
        ("Company profile", row.get("company_profile")),
        ("Description", row.get("description")),
        ("Requirements", row.get("requirements")),
        ("Benefits", row.get("benefits")),
    ]
    rendered = [f"{name}: {clean(value)}" for name, value in parts if clean(value)]
    return "\n".join(rendered)[:20_000]


def convert(row: dict[str, str], index: int) -> dict[str, object]:
    fraud = label_is_fraud(row.get("fraudulent"))
    title = clean(row.get("title")) or "Untitled job"
    industry = clean(row.get("industry"))
    function = clean(row.get("function"))
    return {
        "id": f"emscad_{index:05d}_{'fraud' if fraud else 'real'}",
        "source": "EMSCAD / Real or Fake Job Posting dataset",
        "expected_is_fraud": fraud,
        "expected_verdict": "SPAM" if fraud else "SUPPORTED_FIT",
        "profile": {
            "skills": ["Python", "SQL", "communication", "analysis"],
            "experience": "Early-career candidate evaluating inbound recruiter opportunities.",
        },
        "opportunity": {
            "company": industry or function or "Listed Employer",
            "sender_email": "recruiting@example.com",
            "message": make_message(row),
        },
        "fixture_evidence": {
            "verified": not fraud,
            "reason": (
                "Dataset label marks this posting as fraudulent."
                if fraud
                else "Dataset label marks this posting as legitimate; fixture treats it as supported."
            ),
            "sources": [] if fraud else ["https://example.com/offline-emscad-fixture"],
            "opportunity_supported": not fraud,
            "classification": "suspicious" if fraud else "supported",
        },
        "metadata": {
            "title": title,
            "location": clean(row.get("location")),
            "employment_type": clean(row.get("employment_type")),
            "fraudulent": clean(row.get("fraudulent")),
            "in_balanced_dataset": clean(row.get("in_balanced_dataset")),
        },
    }


def load_rows(path: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader(handle)
        fraud, real = [], []
        for row in reader:
            if not make_message(row):
                continue
            (fraud if label_is_fraud(row.get("fraudulent")) else real).append(row)
    return fraud, real


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--fraud", type=int, default=50, help="Number of fraudulent examples to sample.")
    parser.add_argument("--real", type=int, default=50, help="Number of legitimate examples to sample.")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    fraud_rows, real_rows = load_rows(args.input)
    rng = random.Random(args.seed)
    selected = (
        rng.sample(fraud_rows, min(args.fraud, len(fraud_rows)))
        + rng.sample(real_rows, min(args.real, len(real_rows)))
    )
    rng.shuffle(selected)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(selected, 1):
            handle.write(json.dumps(convert(row, index), ensure_ascii=False) + "\n")

    print(f"Wrote {len(selected)} eval examples to {args.output}")
    print(f"Source rows: {len(fraud_rows)} fraudulent, {len(real_rows)} legitimate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
