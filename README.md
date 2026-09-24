---
title: RecruiterRadar
emoji: 📡
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 5.50.0
app_file: hf_app.py
python_version: "3.12"
pinned: false
---

# RecruiterRadar

Resume-based recruiter opportunity triage with live Groq, Tavily, Gemini fallback,
and configurable LangSmith telemetry. The Streamlit app is the local UI;
`hf_app.py` is the Gradio UI for Hugging Face Spaces.

## Install and run

```sh
uv pip install -r requirements.txt
uv run --no-sync streamlit run app.py
```

Alternatively, use `python -m pip install -r requirements.txt` and
`python -m streamlit run app.py` inside your virtual environment.
`requirements-ui.txt` is a compatibility alias for the full dependency list.
`pyproject.toml` also declares runtime dependencies. The existing `uv.lock` has
not been refreshed; use the requirements command above, or run `uv lock` before
switching to `uv sync`.

Your existing `.env` provides provider configuration. Required keys:
`GROQ_API_KEY`, `TAVILY_API_KEY`, and `GOOGLE_API_KEY` (or `GEMINI_API_KEY`)
for Gemini fallback. Defaults are `openai/gpt-oss-120b` and
`gemini-2.5-flash`; override with `GROQ_MODEL` and `GEMINI_MODEL` if needed for
your account. See `.env.example` for configuration names.

1. Upload a text-based PDF resume and click **Parse resume**. PDF extraction is
   local; Groq converts the extracted text into skills and an experience summary.
2. Review the extracted profile. No manual skills or experience entry is needed.
3. Enter the company and recruiter message, then click **Evaluate opportunity**.
   Local rules run first, followed by Tavily research, LLM evidence assessment,
   and resume-based matching. Insufficient evidence triggers up to two rewritten
   search retries before abstaining.
4. Use **Clear session** to remove the current profile, upload and result.

Provider API requests occur on those submissions, not merely on page load or
ordinary reruns. Groq request failures fall back to Gemini when a Gemini key is
configured. If both providers fail, the app reports both errors so the failing
route is visible. Other failures are shown as errors or abstentions. Evidence gaps can still produce
`ABSTAIN NEEDS HUMAN`.

## Tracing

Set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` to enable telemetry on
submitted actions. `LANGSMITH_PROJECT` defaults to `RecruiterRadar`.
Telemetry includes provider routing, successful-call latency/token counts,
search attempts and outcome, excluding resume text, prompts and messages.
The app does not export raw LangGraph state. Tracing follows your configuration;
it is not forcibly disabled in the environment.

## Offline checks

```sh
python -m unittest discover -s tests -v
python main.py
```

Tests use fake credentials and mocked responses with outbound sockets blocked.
They do not read `.env`. `main.py` remains an explicitly synthetic demo.
Real integration checks are left for you to run from the app.

## Hugging Face Spaces deployment

This repo is ready to deploy as a Gradio-based Hugging Face Space. Create a
blank Gradio Space, then add these Space secrets:

```sh
GROQ_API_KEY
GEMINI_API_KEY
TAVILY_API_KEY
LANGSMITH_API_KEY
LANGSMITH_TRACING
LANGSMITH_PROJECT
GROQ_MODEL
GEMINI_MODEL
```

Only `GROQ_API_KEY`, `GEMINI_API_KEY` and `TAVILY_API_KEY` are required for the
main app flow. `LANGSMITH_*` values are optional telemetry settings.
`GROQ_MODEL` and `GEMINI_MODEL` can be omitted to use the defaults in the app.

To sync from GitHub, set repository variable `HF_SPACE_ID` to the Space id, such
as `your-hf-username/recruiterradar`, and set repository secret `HF_TOKEN` to a
Hugging Face token with write access to the Space. The workflow
`.github/workflows/deploy-huggingface-space.yml` syncs `main` to the Space and
can also be run manually. For this project, use `HF_SPACE_ID=attem03/RecruiterRadar`.

The workflow installs dependencies on Python 3.12, checks compatibility, runs
regression tests, and starts the actual Gradio server before deploying. It uses
the pinned Hugging Face Python SDK instead of `hub-sync` (whose CLI command is
incompatible with newer Hub releases). Only runtime files are uploaded; local
secrets, resumes, notebooks and GitHub configuration are excluded. It then waits
up to 15 minutes for the Space to run and respond to an HTTP health check.
Build/runtime errors fail the workflow; inspect the Space logs for details.
Pull requests run validation without deploying or accessing deployment secrets.

This app calls external inference APIs and does not need a GPU or a `spaces.GPU`
decorator. CPU Basic has no hourly charge, but Hugging Face currently requires a
paid plan for creating compute Spaces (Gradio or Docker). Check your account's
hardware availability before choosing this host. See the
[hardware documentation](https://huggingface.co/docs/hub/spaces-gpus).
The deployment script rejects ZeroGPU before upload and never changes hardware.
ZeroGPU rejects this app with “No @spaces.GPU function detected” because no model
runs on a local GPU. Use CPU hardware if available on your plan, or another
Python application host. Gradio is the application SDK.
API permissions and quotas must still be checked by evaluating a message in the
live Space after deployment; CI does not send resumes to providers.

## Privacy and limitations

The app keeps resumes and profiles in session memory, without a database or
LangGraph checkpointer. Tab closure does not guarantee immediate memory cleanup.
Submitted resume text and opportunity data go to the configured AI providers;
company queries go to Tavily. Scanned PDFs require OCR, which is not implemented.
Company evidence does not authenticate the sender. Latency, provider availability,
account quotas and real-world matching quality require live testing.

Provider request formats follow the official
[Groq API reference](https://console.groq.com/docs/api-reference),
[Gemini GenerateContent reference](https://ai.google.dev/api/generate-content),
[Tavily Search reference](https://docs.tavily.com/documentation/api-reference/endpoint/search),
and [LangSmith tracing documentation](https://docs.langchain.com/langsmith/trace-without-env-vars).

## Message vetting and search decisions

Company existence alone never unlocks fit scoring. The evidence assessment now
receives the message and sender, checks suspicious hiring/payment/data requests,
promotional or sponsored outreach, and corroboration of the role and sender
 affiliation. Suspicious and promotional messages stop before matching. Missing
sender or offer evidence produces abstention. Stealth is reported as an assessment
only when claimed or evidenced, not inferred solely from an empty search.
This is public-evidence triage, not authentication or a guarantee of fraud detection.

The search loop uses a qualitative value-of-information heuristic: retry only when
a distinct targeted query could resolve missing evidence, at most twice after the
initial search. It is not a calibrated numerical VOI model. Final abstention stops
execution; there is no background worker. The UI shows attempt and stopping reasons.

Under Provider configuration, check tracing status and open LangSmith. Select the
RecruiterRadar tracing project (or your configured project), then an
`evaluate_opportunity` or `parse_resume` run. Its metadata `calls` contains provider
usage, search decisions and, for evaluations, node timings/outcomes. These are
redacted summary traces, not full nested graph spans. Flushing telemetry does not
by itself verify server receipt. Raw messages, resumes and search queries are not
included in this metadata. No model training or fine-tuning is performed.
