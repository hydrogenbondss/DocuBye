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
)
from .google import LIVE_FORM_URL, REAL_SOURCE_ENV, _login_wall_visible

ACCOUNT_CONFIRMATION = "I will sign in myself"
DEFAULT_OUTPUT_DIR = "captures/google"

# Two-phase network policy. Documented in docs/integrations/google.md.
#
# AUTH_HOST: accounts.google.com — the human's own sign-in form lives here and
#   its submission is a POST. During the sign-in phase the guard allows
#   GET/POST/HEAD to this host only so the PERSON can authenticate; the agent
#   remains read-only and never sends anything itself. No other auth-domain
#   host is allowed: if Google's redirect chain involves any other host, the
#   run stops with a redacted note instead of widening this list implicitly.
# WIZARD_HOST: support.google.com — the removal wizard. GET/HEAD only, always.
# STATIC_HOSTS: static asset hosts needed to render Google's pages
#   (gstatic = scripts/styles/fonts, fonts.googleapis.com = CSS,
#   google.com/www.google.com = wizard-referenced assets). GET/HEAD only.
# Telemetry endpoints (play.google.com, google-analytics.com,
# googletagmanager.com, ogs.google.com, ...) are NOT in any allowlist and stay
# blocked in both phases.
AUTH_HOST = "accounts.google.com"
WIZARD_HOST = "support.google.com"
STATIC_HOSTS = frozenset({
    "www.gstatic.com", "ssl.gstatic.com", "fonts.gstatic.com", "fonts.googleapis.com",
    "google.com", "www.google.com",
})


def _host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").casefold().rstrip(".")


def _scheme_ok(url: str, host: str) -> bool:
    scheme = urlsplit(url).scheme
    if scheme == "https":
        return True
    # Plain HTTP is accepted only for loopback fixture servers used by tests.
    return scheme == "http" and host == "127.0.0.1"


def signin_phase_allowed(url: str, method: str, *, auth_host: str = AUTH_HOST,
                         wizard_host: str = WIZARD_HOST, static_hosts=frozenset(STATIC_HOSTS)) -> bool:
    """Sign-in phase: the human's auth POSTs to the auth host pass; read-only elsewhere."""
    host = _host_of(url)
    if not host or not _scheme_ok(url, host):
        return False
    verb = method.upper()
    if host == auth_host:
        return verb in {"GET", "POST", "HEAD"}
    if host == wizard_host or host in static_hosts:
        return verb in {"GET", "HEAD"}
    return False


def wizard_phase_allowed(url: str, method: str, *, wizard_host: str = WIZARD_HOST,
                         static_hosts=frozenset(STATIC_HOSTS)) -> bool:
    """Wizard phase: re-locked to GET/HEAD on the wizard and static hosts only."""
    host = _host_of(url)
    if not host or not _scheme_ok(url, host):
        return False
    return method.upper() in {"GET", "HEAD"} and (host == wizard_host or host in static_hosts)


class _TwoPhaseGuard:
    """Sign-in phase permits human auth POSTs; wizard phase is GET/HEAD-only."""

    def __init__(self, notes: list[str], *, auth_host: str, wizard_host: str,
                 static_hosts: frozenset) -> None:
        self.phase = "sign-in"
        self.notes = notes
        self.auth_host = auth_host
        self.wizard_host = wizard_host
        self.static_hosts = static_hosts

    def __call__(self, route) -> None:
        request = route.request
        if self.phase == "sign-in":
            allowed = signin_phase_allowed(
                request.url, request.method,
                auth_host=self.auth_host, wizard_host=self.wizard_host, static_hosts=self.static_hosts,
            )
        else:
            allowed = wizard_phase_allowed(
                request.url, request.method,
                wizard_host=self.wizard_host, static_hosts=self.static_hosts,
            )
        if not allowed:
            parsed = urlsplit(request.url)
            self.notes.append(
                f"Blocked {request.method.upper()} {parsed.hostname or '<invalid>'}{parsed.path[:80]} "
                f"({self.phase} phase)"
            )
            route.abort("blockedbyclient")
            return
        route.continue_()


def _prompt_until_empty(prompt_fn: Callable[[str], str], message: str) -> None:
    """Require an empty Enter; non-empty input (e.g. a pasted command) re-prompts."""
    answer = prompt_fn(message)
    while answer.strip():
        answer = prompt_fn("No input expected here — press Enter alone when ready: ")

# --- Sanitization ------------------------------------------------------------

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
    out = _sub(_DATE_RE, "[redacted-date]", "dates of birth", out)
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
    visibility: str = "unknown"  # "visible" | "hidden" | "absent"


# The real wizard is a single dynamic page: conditional sections exist in the
# DOM before they are revealed. A present-but-hidden control therefore counts
# as found, with its visibility recorded.
EXPECTED_SINGLE_PAGE_LABELS = (
    EXPECTED_CONTACT_STEPS[0],
    EXPECTED_CONTACT_STEPS[1],
    "Other personal information",
    "Government-issued ID document images",
    "Last four characters of the ID",
    "Is the content being shared with malicious, threatening, or harassing intent?",
)
EXPECTED_SINGLE_PAGE_FIELDS = (
    "country", "contact_email", "content_urls", "screenshots",
    "search_results_urls", "search_terms",
)
EXPECTED_SINGLE_PAGE_BUTTONS = ("Next", "Submit")


def _presence(page, locator) -> tuple[str, str]:
    """(status, visibility) for a locator: hidden-but-present counts as found."""
    count = locator.count()
    if count == 0:
        return "missing", "absent"
    visible = sum(1 for i in range(count) if locator.nth(i).is_visible())
    if visible > 1:
        return "ambiguous", "visible"
    if visible == 1:
        return "found", "visible"
    return "found", "hidden"


def validate_selectors(page, step: str) -> list[SelectorCheck]:
    """Machine-readable adapter-vs-DOM comparison. Contains no page content."""
    checks: list[SelectorCheck] = []
    for label in EXPECTED_SINGLE_PAGE_LABELS:
        status, visibility = _presence(page, page.get_by_text(label, exact=True))
        checks.append(SelectorCheck(step, f"text:{label}", status, visibility))
    for name in EXPECTED_SINGLE_PAGE_FIELDS:
        status, visibility = _presence(page, page.locator(f'[name="{name}"]'))
        checks.append(SelectorCheck(step, f"field:{name}", status, visibility))
    for button in EXPECTED_SINGLE_PAGE_BUTTONS:
        status, visibility = _presence(page, page.get_by_role("button", name=button, exact=True))
        checks.append(SelectorCheck(step, f"button:{button}", status, visibility))
    checks.append(SelectorCheck(
        step, "captcha-or-challenge",
        "found" if _verification_challenge_visible(page) else "missing",
        "visible" if _verification_challenge_visible(page) else "absent",
    ))
    checks.append(SelectorCheck(
        step, "login-wall",
        "found" if _login_wall_visible(page) else "missing",
        "visible" if _login_wall_visible(page) else "absent",
    ))
    return checks


# --- Browser session ---------------------------------------------------------

# Live runs use the owner's real Google Chrome (channel="chrome") through a
# persistent profile under the gitignored captures/ directory. Chrome for
# Testing is stonewalled by Google's sign-in flow (automation-flagged binary,
# observed 15 November 2026: sign-in hung after email entry with only
# telemetry blocked). We deliberately apply NO anti-detection measures — no
# navigator.webdriver tampering, no user-agent spoofing, no fingerprint
# tricks. The human performs all authentication in a normal browser binary;
# we do not disguise automation from Google. Tests and fixtures keep the
# Playwright-managed Chromium.


def _launch_session(playwright, *, live: bool, headless: bool, profile_dir: Path):
    """Return (context, browser). browser is None for a persistent context."""
    if live:
        if headless:
            raise ValueError("Live capture requires a headed browser so the owner can sign in")
        try:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                channel="chrome",
                headless=False,
                service_workers="block",
                accept_downloads=False,
            )
        except Exception as exc:
            raise RuntimeError(
                "Google Chrome is not installed or could not be launched. Live capture needs "
                "the owner's real Chrome browser; install Chrome and retry. The offline fixture "
                "path does not require Chrome."
            ) from exc
        return context, None
    browser = playwright.chromium.launch(headless=headless)
    return browser.new_context(service_workers="block", accept_downloads=False), browser


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
                {"step": c.step, "selector": c.description, "status": c.status, "visibility": c.visibility}
                for c in self.checks
            ],
            "notes": self.notes,
        }


def run_capture(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    start_url: str = LIVE_FORM_URL,
    prompt_fn: Callable[[str], str] = input,
    env: dict[str, str] | None = None,
    headless: bool = False,
    live: bool = True,
    auth_host: str = AUTH_HOST,
    wizard_host: str = WIZARD_HOST,
    static_hosts: frozenset = frozenset(STATIC_HOSTS),
) -> CaptureResult:
    """Headed, human-driven read-only capture. Never fills, never submits.

    ``live=True`` (the default) launches the owner's real Chrome against the
    live site and is DEPRECATED: Google stonewalls automation-controlled
    browsers at sign-in and DocuBye does not evade that. The supported
    validation path is manual capture (docubye-google-report). Tests pass
    ``live=False`` with a fixture ``start_url`` to run the same flow offline
    with the Playwright-managed Chromium.
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
    profile_dir = output.parent / "chrome-profile"

    with sync_playwright() as playwright:
        context, browser = _launch_session(
            playwright, live=live, headless=headless, profile_dir=profile_dir
        )
        page = context.pages[0] if context.pages else context.new_page()
        main_page_holder: dict = {"page": page}
        _install_popup_guard(context, main_page_holder)

        guard = _TwoPhaseGuard(
            result.notes, auth_host=auth_host, wizard_host=wizard_host, static_hosts=static_hosts
        )

        def block_websocket(socket_route) -> None:
            result.notes.append(f"Blocked WEBSOCKET {urlsplit(socket_route.url).hostname}")
            socket_route.on_message(lambda _message: None)

        context.route("**/*", guard)
        context.route_web_socket(lambda _url: True, block_websocket)
        try:
            page.goto(start_url, wait_until="domcontentloaded", timeout=30_000)
            _prompt_until_empty(
                prompt_fn,
                "Sign in yourself in the browser window if the form requires it. "
                "The agent does not see credentials. Press Enter alone when the wizard is visible: ",
            )
            resolved = _resolve_working_page(
                context, page,
                lambda url, method: signin_phase_allowed(
                    url, method, auth_host=auth_host, wizard_host=wizard_host, static_hosts=static_hosts
                ),
            )
            if resolved is None:
                result.notes.append("Browser window closed before capture; nothing was saved.")
                return result
            page = resolved
            main_page_holder["page"] = page

            # Verify the wizard actually loaded before proceeding; never produce
            # an empty report from a page that is not the wizard.
            current_host = _host_of(page.url)
            if current_host != wizard_host:
                result.notes.append(
                    f"Wizard domain not loaded after sign-in (host: {current_host or 'none'}); "
                    "paused without capturing. If the redirect chain involved another host, "
                    "it was deliberately not allowlisted."
                )
                return result
            if _login_wall_visible(page):
                result.notes.append("Sign-in wall still visible after human sign-in pause; stopping here.")
                return result

            # Auth is complete: re-lock to GET/HEAD on the wizard domain only.
            guard.phase = "wizard"

            if _verification_challenge_visible(page):
                _prompt_until_empty(
                    prompt_fn,
                    "A CAPTCHA/verification is visible. Solve it yourself in the browser "
                    "(the agent never bypasses it), then press Enter alone; or press Enter to stop: ",
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
            if browser is not None:
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
