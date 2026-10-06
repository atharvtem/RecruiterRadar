"""Live Streamlit app. Requests run only on explicit button submissions."""
from dataclasses import asdict, replace
from hashlib import sha256

import streamlit as st
from langsmith import tracing_context

from recruiterradar import firebase
from recruiterradar.models import Opportunity
from recruiterradar.pipeline import Pipeline
from recruiterradar.providers.base import ProviderUnavailable
from recruiterradar.providers.live import LiveLLM, LiveSearch, Settings, publish_metrics
from recruiterradar.resume import extract_resume
from recruiterradar.ui import style, login


def telemetry(settings, name, metrics, outcome):
    try:
        publish_metrics(settings, name, metrics, outcome)
        st.session_state["telemetry_status"] = f"Telemetry queued/flushed to LangSmith project {settings.project}." if settings.tracing else "LangSmith tracing is disabled."
    except Exception:
        st.session_state["telemetry_status"] = "LangSmith telemetry failed."
        st.warning("Your result is ready, but LangSmith telemetry could not be sent. Check your tracing configuration.")


def auth_panel(settings):
    settings = replace(settings, google_redirect_uri=firebase.redirect_uri(settings, st.context.url))
    if not firebase.configured(settings):
        st.info("Firebase auth is not configured. Usage limits are disabled in this environment.")
        return None, None
    if not firebase.google_configured(settings):
        st.error("Google sign-in is not configured. Add GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI.")
        st.stop()

    params = st.query_params
    code = params.get("code")
    state = params.get("state")
    if code and state:
        if not firebase.verify_oauth_state(settings, state):
            st.error("Login state did not match. Please try again.")
            st.stop()
        try:
            st.session_state["firebase_user"] = firebase.sign_in_with_google_code(settings, code)
            st.query_params.clear()
            st.rerun()
        except ProviderUnavailable as exc:
            st.error(str(exc))
            st.stop()

    user = st.session_state.get("firebase_user")
    if user:
        st.sidebar.subheader("Your workspace")
        st.sidebar.text(user.email)
        if st.sidebar.button("Sign out", icon=":material/logout:"):
            for key in ("firebase_user", "candidate_profile", "result"):
                st.session_state.pop(key, None)
            st.rerun()
        if firebase.is_developer(settings, user):
            st.sidebar.metric("Monthly allowance", "Developer")
            st.sidebar.caption("No app quota. Provider limits still apply.")
            return user, None
        try:
            current = firebase.usage(settings, user)
        except firebase.FirebaseUnavailable as exc:
            st.error(firebase.usage_error_message(exc))
            if st.button("Retry usage check"):
                st.rerun()
            st.stop()
        remaining = max(0, settings.monthly_search_limit - current["searches"])
        st.sidebar.metric("Web searches remaining", f"{remaining} / {settings.monthly_search_limit}")
        st.sidebar.progress(remaining / max(1, settings.monthly_search_limit))
        st.sidebar.caption("Renews each calendar month (UTC).")
        return user, current

    login(settings, firebase.google_auth_url(settings, firebase.oauth_state(settings)))
    st.stop()


st.set_page_config(page_title="RecruiterRadar", page_icon=":material/policy:", layout="wide")
style()
settings_preview = Settings.load()
auth_user, usage_record = auth_panel(settings_preview)
st.title("RecruiterRadar")
st.caption("Opportunity review")
developer = firebase.is_developer(settings_preview, auth_user)
with st.sidebar.expander("Privacy"):
    st.caption("Submitted resumes and messages are sent to AI providers. Company research uses Tavily. Clear workspace removes session data; monthly usage is retained.")
if developer or not auth_user:
    with st.sidebar.expander("Developer diagnostics", expanded=False):
        st.write(f"Groq model: `{settings_preview.groq_model}`")
        st.write(f"Gemini fallback model: `{settings_preview.gemini_model}`")
        st.write(f"Firebase auth: {'enabled' if firebase.configured(settings_preview) else 'disabled'}")
        st.write(f"Monthly Tavily search limit: `{settings_preview.monthly_search_limit}`")
        st.write(f"LangSmith: {'enabled' if settings_preview.tracing else 'disabled'}")
        st.link_button("Open LangSmith tracing projects", "https://smith.langchain.com")

if st.sidebar.button("Clear workspace", icon=":material/restart_alt:"):
    generation = st.session_state.get("generation", 0) + 1
    for key in ("candidate_profile", "result", "resume_fingerprint", "telemetry_status"):
        st.session_state.pop(key, None)
    st.session_state["generation"] = generation
    st.rerun()

generation = st.session_state.get("generation", 0)
st.divider()
st.subheader("01  Resume")
uploaded = st.file_uploader("Resume PDF (up to 5 MB)", type=["pdf"], key=f"resume_{generation}")
fingerprint = sha256(uploaded.getvalue()).hexdigest() if uploaded is not None else None
if fingerprint != st.session_state.get("resume_fingerprint"):
    for key in ("candidate_profile", "result"):
        st.session_state.pop(key, None)
    st.session_state["resume_fingerprint"] = fingerprint

if st.button("Parse resume", disabled=uploaded is None, icon=":material/description:"):
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

st.divider()
st.subheader("02  Opportunity")
with st.form("opportunity", border=False):
    company_col, sender_col = st.columns(2)
    company = company_col.text_input("Company name", max_chars=200)
    sender = sender_col.text_input("Sender email (optional)", max_chars=320)
    message = st.text_area("Recruiter message", max_chars=20_000, height=160)
    with st.expander("Preferences"):
        excluded = st.text_input("Excluded sender domains (comma-separated)")
    submit = st.form_submit_button("Evaluate opportunity", type="primary", icon=":material/search:", disabled="candidate_profile" not in st.session_state)

if submit:
    st.session_state.pop("result", None)
    try:
        remaining_searches = 3
        if auth_user and not developer:
            usage_record = firebase.usage(settings_preview, auth_user)
            remaining_searches = settings_preview.monthly_search_limit - usage_record["searches"]
            if remaining_searches <= 0:
                st.error("Monthly search limit reached. Try again next month.")
                st.stop()
        opportunity = Opportunity(message, sender, company)
        profile = replace(st.session_state["candidate_profile"], excluded_domains=tuple(d.strip() for d in excluded.split(",") if d.strip()))
        settings = Settings.load()
        llm = LiveLLM(settings)
        search = LiveSearch(settings, llm)
        with st.spinner("Checking message risks, company evidence and sender affiliation before job fit…"):
            # Export explicit metadata below, not graph state containing resume data.
            with tracing_context(enabled=False):
                pipeline = Pipeline(search, llm, max_search_attempts=remaining_searches)
                graph = pipeline.compile_graph()
                state = graph.invoke({"profile": profile, "opportunity": opportunity, "attempts": 0})
            result = state["result"]
            st.session_state["result"] = result
            if auth_user and not developer and result.search_attempts:
                st.session_state["usage_record"] = firebase.add_searches(settings_preview, auth_user, result.search_attempts)
            telemetry(settings, "evaluate_opportunity", pipeline.metrics + search.metrics + llm.metrics, result.verdict.value)
            st.rerun()
    except (ValueError, ProviderUnavailable) as exc:
        st.error(str(exc))

if developer and "telemetry_status" in st.session_state:
    st.sidebar.caption(st.session_state["telemetry_status"])

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
