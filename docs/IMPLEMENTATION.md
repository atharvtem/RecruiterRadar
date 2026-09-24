# Implementation and testing checkpoints

## Implemented

- Streamlit live flow: PDF upload, in-memory extraction, Groq profile parsing,
  review of extracted skills and experience, and opportunity evaluation.
- Groq structured JSON responses validated before use; Gemini fallback on Groq
  request failures when a Gemini key is configured. If fallback fails too, both
  provider errors are surfaced together.
- Tavily search, source-constrained company assessment, missing-evidence query
  rewriting, and initial search plus at most two retries.
- Resume-based fit scoring through the LangGraph pipeline; local spam/domain
  exclusions short-circuit company research.
- Explicit submission buttons; no provider requests on startup or rerender.
- `.env` configuration loaded only on submission, never by offline tests.
- Configurable redacted LangSmith action telemetry, with provider latency and
  token usage for successful LLM calls. No raw resume/graph state tracing.
- Controlled missing-key, timeout, HTTP, malformed JSON and invalid score errors.
- Upload replacement invalidates the old profile and result; clear-session action.
- Full dependency list in requirements.txt and matching runtime declarations
  in pyproject.toml. requirements-ui.txt delegates to requirements.txt.

## Verification

20 offline tests pass, including real LangGraph execution using mock transports,
429 fallback, response validation, evidence-source filtering, rewritten queries,
and Streamlit AppTest parsing/evaluation/rerun/clear-session behavior.
Outbound socket connections are blocked. Tests use synthetic input and credentials.
No real provider API requests were made, and the user's `.env` was not inspected
or modified during implementation.

## User-run live checkpoint

Install requirements.txt, restart Streamlit, upload a resume, click Parse resume,
and confirm the extracted profile. Then evaluate a known company's recruiter
message and inspect its fit explanation and evidence links. If tracing is enabled,
check LangSmith for the action metadata. These steps use real API requests.
Fallback is covered with mocks; do not deliberately exhaust quota to test it.

## Remaining limits

Real credentials, account/model access and end-to-end provider responses have not
been tested. The pre-existing uv.lock needs refresh before using uv sync.
OCR, adversarial PDF resource stress tests, and a labeled matching-quality
evaluation dataset remain outside this change. No latency/free-tier guarantees
have been measured. Search evidence cannot authenticate a recruiter's identity.
Session memory cleanup on tab closure is controlled by Streamlit, not guaranteed
immediate. Providers have their own data handling policies.

## September 24 vetting correction

Added message/sender assessment before matching, separate promotional and stealth
assessments, conservative offer-evidence gating, and distinct-query retry decisions.
The qualitative VOI heuristic stops when further search is unlikely to help and
never exceeds three searches. UI shows investigation history and final stop state.
LangSmith metadata now includes graph node timings and outcomes. A read-only live
check confirmed three successful evaluation runs on September 23 in RecruiterRadar.
25 offline tests pass; revised live LLM classification quality is not yet evaluated.
No fine-tuning or training data generation is involved.
