"""Shared presentation for the Streamlit sign-in and evaluation workspace."""

import streamlit as st


def style():
    st.html("""<style>
    .stMainBlockContainer {max-width: 1040px; padding-top: 3.2rem; padding-bottom: 3rem;}
    h1, h2, h3, p {letter-spacing: 0 !important;}
    h1 {font-size: 2rem !important; font-weight: 700 !important;}
    h2 {font-size: 1.2rem !important;}
    h3 {font-size: 1rem !important;}
    [data-testid="stSidebar"] {border-right: 1px solid #dce3e1;}
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {overflow-wrap: anywhere;}
    .stButton button, .stLinkButton a {border-radius: 6px; min-height: 42px;}
    [data-testid="stForm"] {border: 0; padding: 0;}
    [data-testid="stMarkdownContainer"] hr {margin: 1rem 0;}
    .st-key-login {max-width: 460px; margin: 3rem auto 0;}
    .st-key-login h1 {font-size: 2rem !important; overflow-wrap: normal; word-break: normal;}
    .st-key-login [data-testid="stCaptionContainer"] {text-align: center;}
    .brand-line {height: 4px; width: 48px; background: #138477; margin-bottom: 16px;}
    .eyebrow {font-size: 12px; font-weight: 600; color: #67716d; margin-bottom: 0;}
    @media (max-width: 640px) {
      .stMainBlockContainer {padding: 2rem 1rem;}
      .st-key-login {margin-top: 2rem;}
      .st-key-login h1 {font-size: 1.7rem !important;}
    }
    </style>""")


def login(settings, auth_url):
    with st.container(key="login"):
        st.html('<div class="brand-line"></div><div class="eyebrow">OPPORTUNITY RESEARCH</div>')
        st.title("RecruiterRadar")
        st.link_button("Continue with Google", auth_url, type="primary", use_container_width=True)
        st.caption(f"{settings.monthly_search_limit} web searches per month · Free account")
        st.divider()
        st.write("RecruiterRadar checks recruiter messages for scam signals, researches the company, "
                 "and assesses how supported opportunities match your experience.")
        st.markdown("**Get started**\n\n"
                    "1. Sign in and upload your resume PDF.\n"
                    "2. Parse your resume, then paste a recruiter message and company name.\n"
                    "3. Review the risk assessment, sources, and job-fit result when available.")
