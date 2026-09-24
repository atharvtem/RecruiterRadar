"""Live Streamlit app. Requests run only on explicit button submissions."""
from dataclasses import asdict, replace
from hashlib import sha256

import streamlit as st
from langsmith import tracing_context

from recruiterradar.models import Opportunity
from recruiterradar.pipeline import Pipeline
from recruiterradar.providers.base import ProviderUnavailable
from recruiterradar.providers.live import LiveLLM, LiveSearch, Settings, publish_metrics
from recruiterradar.resume import extract_resume


def telemetry(settings, name, metrics, outcome):
    try:
        publish_metrics(settings, name, metrics, outcome)
        st.session_state["telemetry_status"] = f"Telemetry queued/flushed to LangSmith project {settings.project}." if settings.tracing else "LangSmith tracing is disabled."
    except Exception:
        st.session_state["telemetry_status"] = "LangSmith telemetry failed."
        st.warning("Your result is ready, but LangSmith telemetry could not be sent. Check your tracing configuration.")


st.set_page_config(page_title="RecruiterRadar", page_icon="📡")
st.title("RecruiterRadar")
st.caption("Parse your resume, then evaluate a recruiter opportunity using live company research.")
st.caption("Resume text and opportunities are sent to AI providers when you submit. Company searches use Tavily. Application data stays in this session; Clear session removes it from the app.")
with st.expander("Provider configuration", expanded=False):
    settings_preview = Settings.load()
    st.write(f"Groq model: `{settings_preview.groq_model}`")
    st.write(f"Gemini fallback model: `{settings_preview.gemini_model}`")
    st.write(f"LangSmith: {'enabled' if settings_preview.tracing else 'disabled'} · project: `{settings_preview.project}` · key: {'configured' if settings_preview.langsmith_key else 'missing'}")
    st.link_button("Open LangSmith tracing projects", "https://smith.langchain.com")

if st.button("Clear session"):
    generation = st.session_state.get("generation", 0) + 1
    st.session_state.clear()
    st.session_state["generation"] = generation
    st.rerun()

generation = st.session_state.get("generation", 0)
uploaded = st.file_uploader("Resume PDF (up to 5 MB)", type=["pdf"], key=f"resume_{generation}")
fingerprint = sha256(uploaded.getvalue()).hexdigest() if uploaded is not None else None
if fingerprint != st.session_state.get("resume_fingerprint"):
    for key in ("candidate_profile", "result"):
        st.session_state.pop(key, None)
    st.session_state["resume_fingerprint"] = fingerprint

if st.button("Parse resume", disabled=uploaded is None):
    st.session_state.pop("candidate_profile", None)
    st.session_state.pop("result", None)
    try:
        with st.spinner("Reading your resume and extracting skills and experience…"):
            text = extract_resume(uploaded.getvalue())
            settings = Settings.load()
            llm = LiveLLM(settings)
            st.session_state["candidate_profile"] = llm.profile(text)
            telemetry(settings, "parse_resume", llm.metrics, "profile_ready")
    except (ValueError, ProviderUnavailable) as exc:
        st.error(str(exc))

if "candidate_profile" in st.session_state:
    profile = st.session_state["candidate_profile"]
    st.success("Resume profile ready.")
    with st.expander("Skills and experience extracted from your resume", expanded=True):
        st.write(", ".join(profile.skills))
        st.write(profile.experience)

with st.form("opportunity"):
    company = st.text_input("Company name", max_chars=200)
    sender = st.text_input("Sender email (optional)", max_chars=320)
    message = st.text_area("Recruiter message", max_chars=20_000)
    excluded = st.text_input("Excluded sender domains (optional, comma-separated)")
    submit = st.form_submit_button("Evaluate opportunity", disabled="candidate_profile" not in st.session_state)

if submit:
    st.session_state.pop("result", None)
    try:
        opportunity = Opportunity(message, sender, company)
        profile = replace(st.session_state["candidate_profile"], excluded_domains=tuple(d.strip() for d in excluded.split(",") if d.strip()))
        settings = Settings.load()
        llm = LiveLLM(settings)
        search = LiveSearch(settings, llm)
        with st.spinner("Checking message risks, company evidence and sender affiliation before job fit…"):
            # Export explicit metadata below, not graph state containing resume data.
            with tracing_context(enabled=False):
                pipeline = Pipeline(search, llm)
                graph = pipeline.compile_graph()
                state = graph.invoke({"profile": profile, "opportunity": opportunity, "attempts": 0})
            result = state["result"]
            st.session_state["result"] = result
            telemetry(settings, "evaluate_opportunity", pipeline.metrics + search.metrics + llm.metrics, result.verdict.value)
    except (ValueError, ProviderUnavailable) as exc:
        st.error(str(exc))

if "telemetry_status" in st.session_state:
    st.caption(st.session_state["telemetry_status"])

if "result" in st.session_state:
    result = st.session_state["result"]
    st.subheader(result.verdict.value)
    st.write(result.reason)
    st.caption(f"Assessment: {result.assessment} · Searches: {result.search_attempts}")
    if result.investigation:
        with st.expander("Investigation and search decisions"):
            for step in result.investigation:
                st.write(step)
    if result.verdict.value == "ABSTAIN NEEDS HUMAN":
        st.info("Investigation stopped. No background work is running. Submit new evidence to evaluate again.")
    if result.score is not None:
        st.metric("Fit score", f"{result.score}/100")
    for source in result.sources:
        st.link_button("Company evidence", source)
    with st.expander("Result details"):
        st.json(asdict(result))
