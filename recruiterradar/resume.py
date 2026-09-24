"""Extract a PDF in memory. No upload, filesystem writes, or LLM execution."""

from io import BytesIO


def extract_resume(data: bytes) -> str:
    if len(data) > 5 * 1024 * 1024:
        raise ValueError("Resume must be 5 MB or smaller.")
    if not data.startswith(b"%PDF-"):
        raise ValueError("Upload a valid PDF resume.")
    import pdfplumber
    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            if len(pdf.pages) > 15:
                raise ValueError("Resume must be 15 pages or fewer.")
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except ValueError:
        raise
    except Exception:
        raise ValueError("Could not read this PDF. Try an unencrypted, text-based PDF.") from None
    if not text.strip():
        raise ValueError("No text found. Scanned PDFs need OCR, which is not enabled.")
    if len(text) > 60_000:
        raise ValueError("Extracted resume exceeds the 60,000-character limit.")
    return text.strip()
