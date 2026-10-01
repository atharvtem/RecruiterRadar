"""Print a concise Markdown summary for a fixed-evidence prompt eval report."""

import argparse
import json
from pathlib import Path

from run_prompt_evals import metrics


VARIANTS = ("baseline", "few_shot", "critic")


def percent(value):
    return "n/a" if value is None else f"{value * 100:.1f}%"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Path to prompt eval JSON report")
    args = parser.parse_args()

    report = json.loads(args.report.read_text())
    rows = [row for row in report["rows"] if "error" not in row]
    computed = {variant: metrics([row for row in report["rows"] if row["variant"] == variant]) for variant in VARIANTS}
    providers = sorted({metric.get("provider", "unknown") for row in rows for metric in row.get("usage", [])})
    print(f"# Prompt Eval Summary\n")
    print(f"Report: `{args.report}`")
    print(f"Model: `{report['model']}`")
    print(f"Providers seen: `{', '.join(providers) or 'none'}`")
    print(f"Complete: `{report.get('complete')}`")
    print(f"Rows: `{len(rows)}` successful / `{len(report['rows'])}` total")
    print("\n| Variant | Accuracy | Fraud Recall | False Positive Rate | Abstain Rate | Supported Precision | LLM Calls | Tokens |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for variant in VARIANTS:
        item = computed[variant]
        print("| "
              f"{variant} | {percent(item.get('accuracy'))} | {percent(item['fraud_recall'])} | "
              f"{percent(item['false_positive_rate'])} | {percent(item['abstain_rate'])} | "
              f"{percent(item['supported_opportunity_precision'])} | {item['llm_calls']} | {item['tokens']} |")

    print("\n## Pairwise Changes")
    for name, change in report["comparison"].items():
        improved = ", ".join(change["improved"]) or "none"
        regressed = ", ".join(change["regressed"]) or "none"
        print(f"- `{name}`: {change['paired_cases']} paired cases; improved: {improved}; regressed: {regressed}")


if __name__ == "__main__":
    main()
