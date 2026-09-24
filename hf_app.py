"""Gradio entrypoint for Hugging Face Spaces."""

from dataclasses import replace
from pathlib import Path

import gradio as gr

from recruiterradar.models import Opportunity
from recruiterradar.pipeline import Pipeline
from recruiterradar.providers.base import ProviderUnavailable
from recruiterradar.providers.live import LiveLLM, LiveSearch, Settings, publish_metrics
from recruiterradar.resume import extract_resume


def _read_file(uploaded) -> bytes:
    if uploaded is None:
        raise ValueError("Upload a resume PDF.")
    path = Path(uploaded if isinstance(uploaded, str) else uploaded.name)
    return path.read_bytes()


def _format_result(result, telemetry_status):
    lines = [
        f"## {result.verdict.value}",
        "",
        f"**Assessment:** `{result.assessment}`",
    ]
    if result.score is not None:
        lines.append(f"**Fit score:** `{result.score}/100`")
    if result.search_attempts:
        lines.append(f"**Search attempts:** `{result.search_attempts}`")
    lines.extend(["", result.reason])
    if result.sources:
        lines.extend(["", "### Sources"])
        lines.extend(f"- [{source}]({source})" for source in result.sources)
    if result.investigation:
        lines.extend(["", "### Investigation"])
        lines.extend(f"- {item}" for item in result.investigation)
    if telemetry_status:
        lines.extend(["", f"_Telemetry: {telemetry_status}_"])
    return "\n".join(lines)


def evaluate(resume_file, company, sender, message, excluded_domains):
    try:
        text = extract_resume(_read_file(resume_file))
        settings = Settings.load()
        llm = LiveLLM(settings)
        profile = llm.profile(text)
        excluded_text = excluded_domains or ""
        profile = replace(profile, excluded_domains=tuple(d.strip() for d in excluded_text.split(",") if d.strip()))
        opportunity = Opportunity(message=message or "", sender_email=sender or "", company=company or "")
        search = LiveSearch(settings, llm)
        pipeline = Pipeline(search, llm)
        result = pipeline.run(profile, opportunity)
        telemetry_status = ""
        try:
            metrics = llm.metrics + search.metrics + pipeline.metrics
            publish_metrics(settings, "evaluate_opportunity", metrics, {
                "verdict": result.verdict.value,
                "assessment": result.assessment,
                "search_attempts": result.search_attempts,
                "source_count": len(result.sources),
            })
            telemetry_status = f"queued/flushed to LangSmith project {settings.project}" if settings.tracing else "disabled"
        except Exception:
            telemetry_status = "failed"
        return _format_result(result, telemetry_status)
    except (ValueError, ProviderUnavailable) as exc:
        return f"## Could not evaluate\n\n{exc}"


with gr.Blocks(title="RecruiterRadar", theme=gr.themes.Soft(primary_hue="teal")) as demo:
    gr.Markdown(
        "# RecruiterRadar\n"
        "Upload a resume and paste a recruiter message. The app checks company and message evidence before fit scoring."
    )
    with gr.Row():
        resume = gr.File(label="Resume PDF", file_types=[".pdf"])
        with gr.Column():
            company = gr.Textbox(label="Company name", max_lines=1)
            sender = gr.Textbox(label="Sender email (optional)", max_lines=1)
            excluded = gr.Textbox(label="Excluded sender domains (optional, comma-separated)", max_lines=1)
    message = gr.Textbox(label="Recruiter message", lines=10, max_lines=18)
    submit = gr.Button("Evaluate opportunity", variant="primary")
    output = gr.Markdown(label="Result")

    submit.click(
        evaluate,
        inputs=[resume, company, sender, message, excluded],
        outputs=output,
        show_progress="full",
    )


if __name__ == "__main__":
    demo.launch()
