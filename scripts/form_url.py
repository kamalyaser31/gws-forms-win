"""Google Forms URL parsing shared by fetch and response commands."""

import re
import sys
from urllib.parse import urlparse

FORM_PATH = re.compile(r"^/forms/d/([^/]+)/(?:edit|viewform)/?$")
ENCODED_FORM_PATH = re.compile(r"^/forms/d/e/[^/]+/viewform/?$")


def extract_form_id(url: str) -> str:
    """Return a form ID from an authenticated Google Forms URL."""
    parsed_url = urlparse(url)
    if parsed_url.scheme != "https" or parsed_url.netloc != "docs.google.com":
        _exit_invalid_url()

    if ENCODED_FORM_PATH.fullmatch(parsed_url.path):
        print(
            "[ERROR] Encoded viewform URL (/e/...) does not expose the form_id.\n"
            "        Use the Edit URL or --id directly."
        )
        sys.exit(1)

    form_match = FORM_PATH.fullmatch(parsed_url.path)
    if form_match:
        return form_match.group(1)
    _exit_invalid_url()


def _exit_invalid_url() -> None:
    print(
        "[ERROR] Could not extract form_id from URL.\n"
        "        Use: https://docs.google.com/forms/d/<ID>/edit or --id <ID>"
    )
    sys.exit(1)
