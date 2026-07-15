"""Resume (PDF) parsing for the interviewer bot.

The onboarding page uploads a candidate's resume PDF to the ``/api/resume``
endpoint (see ``lokin/runner/run.py``). The raw bytes are handed to
``parse_resume()`` below, and whatever plain text it returns is stored and later
injected into the interviewer's system prompt at the start of the session
(see ``run_bot`` in ``app.py``).

``parse_resume`` is intentionally left as a stub - implement the actual PDF text
extraction here manually (e.g. with pypdf / pdfminer / pymupdf). Returning an
empty string simply means no resume context is added to the prompt, so the rest
of the flow keeps working while this is unimplemented.
"""

# Latest parsed resume text for this dev server process. Single-user dev
# runner, so a module-level value is enough; there is no per-session store.
_latest_resume_text: str = ""


def parse_resume(file_bytes: bytes) -> str:
    """Extract plain text from an uploaded resume PDF.

    Args:
        file_bytes: Raw bytes of the uploaded PDF file.

    Returns:
        The resume as plain text. Return an empty string if nothing could be
        extracted; that just skips resume injection into the prompt.
    """
    # TODO: implement PDF text extraction and return the resume as plain text.
    return ""


def set_resume_text(text: str) -> None:
    """Store the latest parsed resume text for the next interview session."""
    global _latest_resume_text
    _latest_resume_text = text or ""


def get_resume_text() -> str:
    """Return the latest parsed resume text (empty string if none uploaded)."""
    return _latest_resume_text
