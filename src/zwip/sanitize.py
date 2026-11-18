"""Shared best-effort redaction of personal data from captured or recorded text.

Used by the capture harness (HTML snapshots) and the guided core (free-text
notes). This is a privacy screen, not a parser: captures still require operator
review of the redaction diff, and events/store rows should carry as little
personal data as possible in the first place.
"""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"\+\d[\d\s().-]{7,}\d")
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_TOKEN_PARAM_RE = re.compile(
    r"(?i)\b(sid|ssid|hsid|apisid|sapisid|token|sig|signature|session|sessionid|"
    r"state|code|authuser|access_token|id_token|nonce|key)=([^\s&\"'<>)]+)"
)
_ACCOUNT_LABEL_RE = re.compile(r'(?i)(aria-label="[^"]*(?:google account|account)[^"]*")')
_AVATAR_RE = re.compile(r"<img\b[^>]*(?:googleusercontent|avatar|profile)[^>]*>", re.IGNORECASE)
_ACCOUNT_NAME_RE = re.compile(
    r'(?i)(<(?:div|span|a|button)[^>]*(?:aria-label="[^"]*google account[^"]*"|'
    r'data-ogpc|gb_[a-z])[^>]*>)(.*?)(</(?:div|span|a|button)>)',
    re.DOTALL,
)


def sanitize_html(html: str) -> tuple[str, list[str]]:
    """Redact personal data from text or HTML.

    Returns the sanitized text and the list of redaction kinds applied.
    """
    applied: list[str] = []

    def _sub(pattern, replacement, kind, text):
        new_text, count = pattern.subn(replacement, text)
        if count:
            applied.append(f"{kind} ({count})")
        return new_text

    out = html
    out = _sub(_EMAIL_RE, "[redacted-email]", "emails", out)
    out = _sub(_PHONE_RE, "[redacted-phone]", "phone numbers", out)
    out = _sub(_DATE_RE, "[redacted-date]", "dates of birth", out)
    out = _sub(_TOKEN_PARAM_RE, r"\1=[redacted-param]", "URL/session parameters", out)
    out = _sub(_ACCOUNT_LABEL_RE, 'aria-label="[redacted-account-label]"', "account labels", out)
    out = _sub(_AVATAR_RE, "<!-- [redacted-avatar] -->", "avatar images", out)
    out = _sub(_ACCOUNT_NAME_RE, r"\1[redacted-account-name]\3", "account name areas", out)
    return out, applied
