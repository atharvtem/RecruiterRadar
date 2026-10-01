# RecruiterRadar

[Live App](https://recruiterradar.streamlit.app/)

RecruiterRadar is an AI-powered recruiter outreach screening tool. It parses a candidate resume, investigates inbound recruiter messages with live web evidence, and returns a risk-aware opportunity assessment with a percentage-based fit score.

The project is designed for early-career job seekers who need to quickly distinguish credible opportunities from vague, promotional, or suspicious outreach.

## Features

- Resume-aware opportunity scoring from uploaded PDF resumes.
- LangGraph workflow for triage, web investigation, and final fit assessment.
- Tavily-powered search loop that retries with targeted follow-up queries when evidence is incomplete.
- Groq primary LLM calls with Gemini fallback for provider resilience.
- Suspicious outreach checks for sender affiliation, role evidence, promotional messaging, payment/data requests, and unsupported claims.
- Optional LangSmith telemetry with redacted metadata for latency, token usage, search attempts, and workflow outcomes.
- Streamlit UI for the live app and Gradio entrypoint for Hugging Face Spaces deployment.

## How It Works

1. Upload a text-based PDF resume.
2. RecruiterRadar extracts skills and experience from the resume.
3. Paste the company name, sender email, and recruiter message.
4. The app checks local risk rules, researches the company and opportunity, and validates evidence from public sources.
5. If the opportunity is supported, the app returns a fit score and explanation. If evidence is missing or risky, it abstains or flags the message before scoring.

## Tech Stack

- **Python 3.12**
- **Streamlit** for the public web app
- **LangGraph** for workflow orchestration
- **Groq** for primary structured LLM responses
- **Gemini** for fallback LLM responses
- **Tavily** for web research
- **LangSmith** for optional redacted tracing
- **Gradio / Hugging Face Spaces** for alternate deployment support

## Local Setup

Clone the repository and install dependencies:

```sh
python -m pip install -r requirements.txt
```

Create a `.env` file using `.env.example` as a reference:

```sh
GROQ_API_KEY=
GOOGLE_API_KEY=
TAVILY_API_KEY=
LANGSMITH_API_KEY=
LANGSMITH_TRACING=false
GROQ_MODEL=openai/gpt-oss-120b
GEMINI_MODEL=gemini-3.5-flash-lite
LANGSMITH_PROJECT=RecruiterRadar
```

Run the Streamlit app:

```sh
python -m streamlit run app.py
```

You can also run with `uv`:

```sh
uv pip install -r requirements.txt
uv run --no-sync streamlit run app.py
```

## Testing

Run the offline regression suite:

```sh
python -m unittest discover -s tests -v
```

The tests use mocked providers and fake credentials. They do not read `.env` or make live provider calls.

## Offline Evals

Build a small balanced eval sample from the raw EMSCAD-style CSV:

```sh
python3 scripts/build_eval_dataset.py
```

Run quota-free evals:

```sh
python3 scripts/run_evals.py
```

These evals do not call Tavily or live LLM providers. The pipeline fixture eval checks workflow behavior with mocked evidence, while the keyword baseline reports local fraud-detection metrics against the dataset labels. Live Tavily smoke tests should stay separate and tiny because each production evaluation can use up to three search calls.

### Fixed-Evidence Prompt Benchmark

Validate inputs without making API calls, then run the three-way comparison:

```sh
.venv/bin/python scripts/run_prompt_evals.py
.venv/bin/python scripts/run_prompt_evals.py --live
.venv/bin/python scripts/run_prompt_evals.py --live --allow-fallback
.venv/bin/python scripts/summarize_prompt_eval.py data/evals/results/prompt_eval_gemini35_flash_lite.json
```

This uses the production vetting prompt with baseline, few-shot, and few-shot plus
critic variants on the same 25 recruiter messages. It makes at most 100 LLM calls
per complete run and zero Tavily calls. By default, Gemini fallback is disabled to
keep the model constant. Add `--allow-fallback` when Groq refuses the configured
model and you want the production Gemini fallback behavior. Successful cases are
checkpointed; rerun the same command to resume. Use
`--limit 3 --output /tmp/prompt-smoke.json` for a small smoke test.
Results are saved to `data/evals/results/prompt_eval.json`, including predictions,
reasons, citations, token usage, model, input fingerprint and paired regressions.
The completed Gemini eval is documented in `docs/PROMPT_EVAL_RESULTS.md`.

Fraud recall is detected fraud / labeled fraud; false positives count nonfraud
flagged as fraud. Abstain rate counts unverified and stealth classifications.
Supported-opportunity precision is correctly supported / all predicted supported.
Undefined ratios are null. Provider failures are reported separately and stop the
run; partial results must not be presented as a completed benchmark.

Completed prompt benchmark result:

| Variant | Accuracy | Fraud Recall | False Positive Rate | Abstain Rate | Supported Precision |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 96.0% | 100.0% | 0.0% | 8.0% | 100.0% |
| few-shot | 100.0% | 100.0% | 0.0% | 4.0% | 100.0% |
| critic | 96.0% | 92.3% | 0.0% | 4.0% | 100.0% |

Few-shot prompting is the production default because it improved abstention
behavior without increasing false positives or reducing fraud recall. The critic
agent remains experimental because it doubled LLM calls and regressed one fraud
case in this benchmark.

The evidence file contains **synthetic** excerpts, not retrieved facts about the
named employers. Gold labels are never supplied to either agent. These are vetting
metrics, not resume-fit accuracy or end-to-end retrieval accuracy. The earlier
offline fixture score checks routing using label-derived evidence, not detection.
The 25 hand-authored cases are a pilot, with only one abstention case and no labeled
promotions; they cannot establish real-world accuracy or statistically reliable
improvement. Add independently reviewed ambiguous, benign, and promotional cases
and a held-out test set before tuning further. Few-shot examples are separately
authored fictional cases. Production continues to use the baseline by default;
`LiveSearch(..., prompt_variant="critic")` enables the experimental second agent.
Production uses `prompt_variant="few_shot"` by default.

## Deployment

The production app is deployed on Streamlit Community Cloud:

[https://recruiterradar.streamlit.app/](https://recruiterradar.streamlit.app/)

The repository also includes `hf_app.py` and deployment scripts for a Gradio-based Hugging Face Space. GitHub Actions can validate dependencies, run tests, start the Gradio server, and sync runtime files to a configured Space.

## Privacy and Limitations

- Resume text and recruiter messages are sent to configured AI providers only after explicit user submission.
- Company research queries are sent to Tavily.
- The app stores data in session memory and does not use a database.
- Scanned PDFs require OCR, which is not currently implemented.
- Public evidence can support or reject an opportunity, but it cannot fully authenticate mailbox ownership or guarantee recruiter legitimacy.

## Project Goal

RecruiterRadar reduces manual recruiter-message triage by combining resume parsing, source-grounded company research, and LLM-based fit assessment into a fast, structured workflow for job seekers.
