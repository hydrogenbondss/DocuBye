"""Live read-only capture harness for the Google contact-removal flow.

Headed-only, human-in-the-loop tooling for validating the adapter's read path
against the live site. The person signs in themselves; the agent never touches
credentials, never fills a field, and never clicks Submit. Snapshots are
sanitized (names, emails, phone numbers, avatars, tokens, session identifiers)
and the redaction diff is shown before anything is written to disk. The output
directory is gitignored by default.

Requires DOCUBYE_REAL_SOURCE=1 and an explicit typed account confirmation.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from ..google_inspect import (
    EXPECTED_CONTACT_STEPS,
    _click_unique_visible_text,
    _install_popup_guard,
    _resolve_working_page,
    _verification_challenge_visible,
    inspection_request_allowed,
)
from .google import LIVE_FORM_URL, REAL_SOURCE_ENV, _login_wall_visible

ACCOUNT_CONFIRMATION = "I will sign in myself"
DEFAULT_OUTPUT_DIR = "captures/google"

# --- Sanitization ------------------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"\+\d[\d\s().-]{7,}\d")
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
    """Best-effort redaction of personal data from a captured page.

    Returns the sanitized HTML and the list of redaction kinds applied. This is
    a privacy screen, not a parser: the redaction diff is always shown to the
    operator before saving, and captures stay in a gitignored directory.
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
    out = _sub(_TOKEN_PARAM_RE, r"\1=[redacted-param]", "URL/session parameters", out)
    out = _sub(_ACCOUNT_LABEL_RE, 'aria-label="[redacted-account-label]"', "account labels", out)
    out = _sub(_AVATAR_RE, "<!-- [redacted-avatar] -->", "avatar images", out)
    out = _sub(_ACCOUNT_NAME_RE, r"\1[redacted-account-name]\3", "account name areas", out)
    return out, applied


def redaction_diff(original: str, sanitized: str, context: int = 1) -> str:
    """Unified diff limited to changed hunks, for operator review before saving."""
    diff = difflib.unified_diff(
        original.splitlines(), sanitized.splitlines(),
        fromfile="captured.html", tofile="sanitized.html", n=context, lineterm="",
    )
    return "\n".join(diff)


# --- Selector validation -----------------------------------------------------

@dataclass(slots=True)
class SelectorCheck:
    step: str
    description: str
    status: str  # "found" | "missing" | "ambiguous"


def _label_status(page, label: str) -> str:
    matches = page.get_by_text(label, exact=True)
    visible = [matches.nth(i) for i in range(matches.count()) if matches.nth(i).is_visible()]
    if len(visible) == 1:
        return "found"
    return "ambiguous" if len(visible) > 1 else "missing"


def validate_selectors(page, step: str) -> list[SelectorCheck]:
    """Machine-readable adapter-vs-DOM comparison. Contains no page content."""
    checks: list[SelectorCheck] = []
    for label in EXPECTED_CONTACT_STEPS:
        checks.append(SelectorCheck(step, f"text:{label}", _label_status(page, label)))
    for button in ("Next", "Submit"):
        checks.append(SelectorCheck(step, f"button:{button}", _label_status(page, button)))
    checks.append(SelectorCheck(
        step, "captcha-or-challenge",
        "found" if _verification_challenge_visible(page) else "missing",
    ))
    checks.append(SelectorCheck(step, "login-wall", "found" if _login_wall_visible(page) else "missing"))
    return checks


# --- Capture flow ------------------------------------------------------------

@dataclass(slots=True)
class CaptureResult:
    saved_files: list[str] = field(default_factory=list)
    checks: list[SelectorCheck] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def report(self) -> dict[str, object]:
        return {
            "saved_files": self.saved_files,
            "selector_checks": [
                {"step": c.step, "selector": c.description, "status": c.status} for c in self.checks
            ],
            "notes": self.notes,
        }


def run_capture(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    start_url: str = LIVE_FORM_URL,
    allow_request: Callable[[str, str], bool] = inspection_request_allowed,
    prompt_fn: Callable[[str], str] = input,
    env: dict[str, str] | None = None,
    headless: bool = False,
) -> CaptureResult:
    """Headed, human-driven read-only capture. Never fills, never submits.

    ``start_url``, ``allow_request``, and ``headless`` exist so tests can run
    the same flow offline against sanitized fixtures; production use keeps the
    defaults (live URL, live guard, headed).
    """
    env = os.environ if env is None else env
    if env.get(REAL_SOURCE_ENV) != "1":
        raise RuntimeError(f"Live capture requires explicit opt-in: set {REAL_SOURCE_ENV}=1")

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install dependencies with: pip install -e '.[dev]'") from exc

    confirmation = prompt_fn(
        "This opens a HEADED browser on the live Google removal form.\n"
        "You must sign in yourself; the agent never sees or enters credentials.\n"
        f"Type '{ACCOUNT_CONFIRMATION}' to continue: "
    )
    if confirmation.strip() != ACCOUNT_CONFIRMATION:
        raise PermissionError("Live capture cancelled: explicit account confirmation is required")

    result = CaptureResult()
    output = Path(output_dir)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(service_workers="block", accept_downloads=False)
        main_page_holder: dict = {}
        _install_popup_guard(context, main_page_holder)

        def guard(route) -> None:
            request = route.request
            if not allow_request(request.url, request.method):
                result.notes.append(
                    f"Blocked {request.method.upper()} {urlsplit(request.url).hostname}"
                )
                route.abort("blockedbyclient")
                return
            route.continue_()

        def block_websocket(socket_route) -> None:
            result.notes.append(f"Blocked WEBSOCKET {urlsplit(socket_route.url).hostname}")
            socket_route.on_message(lambda _message: None)

        context.route("**/*", guard)
        context.route_web_socket(lambda _url: True, block_websocket)
        page = context.new_page()
        main_page_holder["page"] = page
        try:
            page.goto(start_url, wait_until="domcontentloaded", timeout=30_000)
            prompt_fn(
                "Sign in yourself in the browser window if the form requires it. "
                "The agent does not see credentials. Press Enter here when the form is visible: "
            )
            resolved = _resolve_working_page(context, page, allow_request)
            if resolved is None:
                result.notes.append("Browser window closed before capture; nothing was saved.")
                return result
            page = resolved
            main_page_holder["page"] = page

            if _login_wall_visible(page):
                result.notes.append("Sign-in wall still visible after human sign-in pause; stopping here.")
                return result
            if _verification_challenge_visible(page):
                prompt_fn(
                    "A CAPTCHA/verification is visible. Solve it yourself in the browser "
                    "(the agent never bypasses it), then press Enter; or press Enter to stop: "
                )
                if _verification_challenge_visible(page):
                    result.notes.append("Verification challenge still visible; capture stopped before branch selection.")
                    return result

            steps = ["landing", "personal-branch", "contact-branch"]
            for index, step in enumerate(steps):
                result.checks.extend(validate_selectors(page, step))
                raw = page.content()
                sanitized, applied = sanitize_html(raw)
                diff = redaction_diff(raw, sanitized)
                print(f"\n--- Redaction diff for step '{step}' ({', '.join(applied) or 'nothing found'}) ---")
                print(diff or "(no changes)")
                decision = prompt_fn(f"Type 'save' to write the sanitized snapshot for step '{step}': ")
                if decision.strip().casefold() == "save":
                    output.mkdir(parents=True, exist_ok=True)
                    path = output / f"{index + 1:02d}-{step}.html"
                    path.write_text(sanitized, encoding="utf-8")
                    result.saved_files.append(str(path))
                else:
                    result.notes.append(f"Operator declined to save the snapshot for step '{step}'.")

                if step == "landing":
                    if not _click_unique_visible_text(page, EXPECTED_CONTACT_STEPS[0]):
                        result.notes.append("Personal-information branch control missing or ambiguous; capture stopped.")
                        return result
                elif step == "personal-branch":
                    if not _click_unique_visible_text(page, EXPECTED_CONTACT_STEPS[1]):
                        result.notes.append("Contact-info sub-branch control missing or ambiguous; capture stopped.")
                        return result
                    page.wait_for_timeout(300)
            result.notes.append(
                "Capture finished at the contact-info branch. No fields were filled, no submit "
                "control was clicked, and no request body was sent."
            )
            return result
        except PlaywrightError as exc:
            result.notes.append(f"Capture stopped safely: {type(exc).__name__}.")
            return result
        finally:
            context.close()
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Headed live read-only capture of the Google removal wizard. Never submits."
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Gitignored capture directory")
    args = parser.parse_args()
    result = run_capture(output_dir=args.output_dir)
    print("\nSelector validation report (no page content):")
    print(json.dumps(result.report(), indent=2))


if __name__ == "__main__":
    main()
