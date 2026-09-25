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
GEMINI_MODEL=gemini-2.5-flash
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
