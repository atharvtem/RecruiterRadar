# Fixed-Evidence Prompt Evaluation Results

This document summarizes the prompt evaluation run for RecruiterRadar's recruiter-message vetting step. The goal was to compare three prompt strategies before deciding what to ship:

1. Baseline production vetting prompt.
2. Few-shot vetting prompt with calibration examples.
3. Few-shot prompt plus a separate critic agent.

The benchmark used fixed evidence documents and did not call Tavily. This isolates prompt behavior from search quality and protects Tavily quota.

## Dataset

The eval used `data/evals/recruiter_messages.jsonl` with 25 labeled recruiter-message cases:

- 13 fraud/spam cases.
- 11 supported recruiting opportunities.
- 1 abstain or human-review case.

The evidence file was `data/evals/recruiter_evidence.json`. It contains synthetic fixed source excerpts for the test cases. Because the evidence is synthetic and the dataset is small, these numbers should be treated as a prompt-regression benchmark, not a broad real-world accuracy claim.

## Run

Final report:

```text
data/evals/results/prompt_eval_gemini35_flash_lite.json
```

Summary command:

```sh
.venv/bin/python scripts/summarize_prompt_eval.py data/evals/results/prompt_eval_gemini35_flash_lite.json
```

The saved report label says `openai/gpt-oss-120b with gemini-3.5-flash-lite fallback` because the run originally started in fallback mode. The successful row-level provider trace shows Gemini handled the completed calls.

## Metrics

| Variant | Accuracy | Fraud Recall | False Positive Rate | Abstain Rate | Supported Precision | LLM Calls | Tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 96.0% | 100.0% | 0.0% | 8.0% | 100.0% | 25 | 15038 |
| few-shot | 100.0% | 100.0% | 0.0% | 4.0% | 100.0% | 25 | 26311 |
| critic | 96.0% | 92.3% | 0.0% | 4.0% | 100.0% | 50 | 58407 |

Definitions:

- Accuracy: predictions matching the labeled target.
- Fraud recall: labeled fraud cases classified as suspicious.
- False positive rate: non-fraud cases incorrectly classified as suspicious.
- Abstain rate: cases classified as unverified or stealth, normalized to abstain.
- Supported precision: predicted supported opportunities that were actually labeled supported.

## Step-By-Step Findings

### 1. Baseline

Baseline was already strong:

- It caught all 13 fraud cases.
- It produced no false positives.
- It abstained on 2 cases.
- It reached 96.0% accuracy.

The miss was `stealth_verified_015`. Baseline had enough evidence to support the opportunity but still abstained because the company was described as stealth. The reason text showed that it recognized the official career page and sender affiliation, but the final class remained abstain.

### 2. Few-Shot Prompting

Few-shot improved the benchmark:

- Accuracy improved from 96.0% to 100.0%.
- Fraud recall stayed at 100.0%.
- False positives stayed at 0.0%.
- Abstain rate dropped from 8.0% to 4.0%.
- Supported precision stayed at 100.0%.

The improvement came from `stealth_verified_015`. The examples helped the model distinguish between "stealth is unsupported and risky" and "stealth is explicitly corroborated by supplied evidence." In that case, the source corroborated the stealth startup, the role, and sender affiliation, so few-shot correctly classified it as supported.

Few-shot costs more tokens than baseline because the prompt includes calibration examples. In this run, it used 26311 tokens versus 15038 for baseline, but the number of LLM calls stayed the same.

### 3. Critic Agent

The critic agent did not improve the benchmark:

- Accuracy fell back to 96.0%.
- Fraud recall dropped from 100.0% to 92.3%.
- False positives stayed at 0.0%.
- Supported precision stayed at 100.0%.
- LLM calls doubled from 25 to 50.

The regression was `spam_recruiting_platform_025`. Few-shot correctly marked it suspicious because it required payment to unlock hidden job offers. The critic changed the classification to promotional. That is safer than marking it supported, but it weakened fraud recall and failed the target label.

## Decision

Use the few-shot prompt as the production default.

Keep the critic agent code available as an experimental option, but do not enable it by default. On this benchmark, critic increased cost and introduced a regression instead of improving quality.

## Interview Summary

RecruiterRadar now has a fixed-evidence prompt evaluation loop. We measured baseline, few-shot prompting, and a critic-agent variant across fraud recall, false positives, abstention, supported-opportunity precision, and overall accuracy. Few-shot prompting improved accuracy from 96.0% to 100.0% while preserving 100.0% fraud recall and 0.0% false positives. The critic agent did not improve results; it doubled LLM calls and reduced fraud recall, so we kept it experimental instead of shipping it.

## Next Benchmark Improvements

The next eval iteration should add more ambiguous benign messages, promotional recruiting-platform messages, and real-source evidence cases. The current benchmark is useful for prompt regression testing, but the small synthetic evidence set is not enough to claim real-world classifier accuracy.
