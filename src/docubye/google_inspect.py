"""Read-only inspection of Google's public personal-contact removal form.

The optional human-handoff mode leaves a visible browser open for operator
observation, but keeps exactly the same read-only network policy. It never
fills fields, captures input values, or submits a report.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from .sources.google_search_contact import GOOGLE_FORM_URL

ALLOWED_READ_HOSTS = {
    "support.google.com",
    "google.com",
    "www.google.com",
    "gstatic.com",
    "www.gstatic.com",
    "ssl.gstatic.com",
    "fonts.gstatic.com",
}
BLOCKED_HOSTS = {"accounts.google.com", "myaccount.google.com"}
BLOCKED_PATH_RE = re.compile(
    r"/(?:submit(?:request)?|formresponse|send(?:report)?)(?:/|$)",
    re.IGNORECASE,
)
EXPECTED_CONTACT_STEPS = [
    "Content contains your personal information",
    "Address, phone number, and/or e-mail address",
]

HUMAN_HANDOFF_PROMPT = """\
DocuBye is paused for a human, read-only inspection.

Use only the browser window opened by this command. You may inspect the public
wizard and select navigation choices, but do NOT sign in, enter or paste any
personal information, upload files, or click Submit.

The network guard remains active: only HTTPS GET/HEAD requests to its small
Google-host allowlist are permitted. Every POST/PUT/PATCH/DELETE request,
unapproved host, WebSocket, and known submission endpoint is blocked. A
CAPTCHA or a Next button may therefore remain unusable. Do not try to bypass
that restriction or switch to an authenticated browser profile.

Navigate only as far as the address/phone/email branch, stopping before any
personal-data fields. Press Enter here when you are done observing, or use
Ctrl+C to stop. DocuBye will record visible labels and field metadata only;
it will not read input values, cookies, request bodies, or screenshots.

Press Enter to capture the current visible metadata: """


@dataclass(frozen=True, slots=True)
class VisibleField:
    tag: str
    field_type: str
    name: str
    element_id: str
    label: str
    placeholder: str
    required: bool
    disabled: bool


@dataclass(slots=True)
class InspectionReport:
    start_url: str
    final_url: str = ""
    selected_steps: list[str] = field(default_factory=list)
    visible_fields: list[VisibleField] = field(default_factory=list)
    visible_buttons: list[str] = field(default_factory=list)
    blocked_hosts: list[str] = field(default_factory=list)
    blocked_requests: list[dict[str, str]] = field(default_factory=list)
    verification_challenge_detected: bool = False
    human_handoff_offered: bool = False
    human_handoff_used: bool = False
    verification_challenge_resolved: bool = False
    submitted: bool = False
    filled_fields: bool = False
    notes: list[str] = field(default_factory=list)


def inspection_request_allowed(url: str, method: str) -> bool:
    """Allow only read methods to an explicit set of public Google hosts."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme != "https" or host not in ALLOWED_READ_HOSTS:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    if port not in {None, 443}:
        return False
    if host in BLOCKED_HOSTS or method.upper() not in {"GET", "HEAD"}:
        return False
    if BLOCKED_PATH_RE.search(parsed.path):
        return False
    return True


def websocket_inspection_allowed(_url: str) -> bool:
    """The inspector never opens or forwards WebSocket connections."""
    return False


def _safe_report_url(url: str) -> str:
    """Remove query strings and fragments before adding a URL to the report."""
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _verification_challenge_visible(page) -> bool:
    """Return true when a visible CAPTCHA/human-verification element is present."""
    return bool(page.locator(
        'iframe[src*="recaptcha"], iframe[title*="recaptcha" i], iframe[title*="challenge" i], '
        '.g-recaptcha, [data-sitekey], [id*="captcha" i], [class*="captcha" i]'
    ).evaluate_all(
        """elements => elements.some(el => {
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return !el.hidden && style.display !== 'none' && style.visibility !== 'hidden'
                && rect.width > 0 && rect.height > 0;
        })"""
    ))


def _safe_to_inspect_without_handoff(page) -> bool:
    """The automatic wizard must stop before interaction if verification is visible."""
    return not _verification_challenge_visible(page)


def _click_unique_visible_text(page, label: str) -> bool:
    matches = page.get_by_text(label, exact=True)
    visible = []
    for index in range(matches.count()):
        candidate = matches.nth(index)
        if candidate.is_visible():
            visible.append(candidate)
    if len(visible) != 1:
        return False
    visible[0].click(timeout=4_000)
    return True


def _visible_field_metadata(page) -> tuple[list[VisibleField], list[str]]:
    """Read visible field attributes, deliberately excluding all input values."""
    records = page.locator("input, textarea, select, button").evaluate_all(
        """elements => elements.filter(el => {
            if (el.hidden || el.getAttribute('aria-hidden') === 'true') return false;
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden'
                && rect.width > 0 && rect.height > 0;
        }).map(el => ({
            tag: el.tagName.toLowerCase(),
            type: (el.type || '').toString(),
            name: (el.name || '').toString(),
            id: (el.id || '').toString(),
            label: el.labels && el.labels.length
                ? Array.from(el.labels).map(item => item.textContent.trim()).join(' ')
                : (el.getAttribute('aria-label') || '').toString(),
            placeholder: (el.getAttribute('placeholder') || '').toString(),
            required: !!el.required,
            disabled: !!el.disabled,
            text: el.tagName.toLowerCase() === 'button' ? (el.innerText || '').trim() : ''
        }))"""
    )
    fields: list[VisibleField] = []
    buttons: list[str] = []
    for record in records:
        if record["tag"] == "button":
            if record["text"]:
                buttons.append(str(record["text"])[:120])
        else:
            fields.append(
                VisibleField(
                    tag=str(record["tag"]),
                    field_type=str(record["type"])[:40],
                    name=str(record["name"])[:120],
                    element_id=str(record["id"])[:120],
                    label=str(record["label"])[:160],
                    placeholder=str(record["placeholder"])[:120],
                    required=bool(record["required"]),
                    disabled=bool(record["disabled"]),
                )
            )
    return fields, buttons


def _selected_choice_labels(page) -> list[str]:
    """Read labels for selected radio choices, never their values."""
    records = page.locator(
        'input[type="radio"]:checked, [role="radio"][aria-checked="true"]'
    ).evaluate_all(
        """elements => elements.map(el => {
            const labels = el.labels ? Array.from(el.labels).map(label => label.innerText.trim()) : [];
            const labelledBy = (el.getAttribute('aria-labelledby') || '').split(/\\s+/).filter(Boolean);
            const referenced = labelledBy.map(id => document.getElementById(id)?.innerText || '').join(' ');
            const text = labels.join(' ') || el.getAttribute('aria-label') || referenced || el.innerText || '';
            return text.trim();
        }).filter(Boolean)"""
    )
    return [str(label)[:160] for label in records]


def _perform_human_handoff(
    page,
    report: InspectionReport,
    prompt_fn: Callable[[str], str],
) -> None:
    """Pause for a person while retaining the read-only request guard."""
    challenge_before = _verification_challenge_visible(page)
    report.verification_challenge_detected = (
        report.verification_challenge_detected or challenge_before
    )
    report.human_handoff_offered = True

    prompt_fn(HUMAN_HANDOFF_PROMPT)
    report.human_handoff_used = True

    report.final_url = _safe_report_url(page.url)
    report.selected_steps = _selected_choice_labels(page)
    report.visible_fields, report.visible_buttons = _visible_field_metadata(page)

    challenge_after = _verification_challenge_visible(page)
    report.verification_challenge_detected = (
        report.verification_challenge_detected or challenge_after
    )
    if challenge_before and not challenge_after:
        report.verification_challenge_resolved = True
        report.notes.append(
            "The operator returned after the previously visible verification element disappeared. "
            "This records browser state only; it does not establish identity or form eligibility."
        )
    elif challenge_after:
        report.notes.append(
            "A CAPTCHA/human-verification element remains visible. The read-only handoff stopped here; "
            "DocuBye did not bypass it."
        )
    else:
        report.notes.append(
            "The operator returned from manual observation. Selected radio labels and visible field "
            "metadata were recorded; no input values were read."
        )

    if report.blocked_requests:
        report.notes.append(
            f"{len(report.blocked_requests)} request(s) were blocked by the read-only guard. "
            "Inspect the method, host, and path metadata before deciding whether the wizard can proceed safely."
        )

    report.notes.append(
        "Human handoff captured no input values, cookies, request bodies, screenshots, or personal-data content. "
        "No fields were filled and no request was submitted."
    )


def inspect_google_contact_form(
    *,
    headless: bool = True,
    human_handoff: bool = False,
    prompt_fn: Callable[[str], str] | None = None,
) -> InspectionReport:
    """Inspect the public form, optionally pausing for guarded human observation."""
    if human_handoff and headless:
        raise ValueError("Human handoff requires a visible browser; pass headless=False")

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Install dependencies with: pip install -e '.[dev]'") from exc

    prompt_fn = prompt_fn or input
    report = InspectionReport(start_url=GOOGLE_FORM_URL)

    def guard(route) -> None:
        request = route.request
        parsed = urlsplit(request.url)
        host = (parsed.hostname or "<invalid-url>").casefold().rstrip(".")
        if not inspection_request_allowed(request.url, request.method):
            if host not in report.blocked_hosts:
                report.blocked_hosts.append(host)
            report.blocked_requests.append({
                "method": request.method.upper(),
                "host": host,
                "path": parsed.path[:160],
            })
            route.abort("blockedbyclient")
            return
        route.continue_()

    def block_websocket(socket_route) -> None:
        parsed = urlsplit(socket_route.url)
        host = (parsed.hostname or "<invalid-url>").casefold().rstrip(".")
        if host not in report.blocked_hosts:
            report.blocked_hosts.append(host)
        # Deliberately do not call connect_to_server().
        socket_route.on_message(lambda _message: None)

    with sync_playwright() as playwright:
        executable_path = os.getenv("DOCUBYE_CHROMIUM_EXECUTABLE") or None
        browser = playwright.chromium.launch(headless=headless, executable_path=executable_path)
        context = browser.new_context(service_workers="block", accept_downloads=False)
        context.route("**/*", guard)
        context.route_web_socket(lambda _url: True, block_websocket)
        page = context.new_page()
        page.set_default_timeout(6_000)

        def close_popup(new_page) -> None:
            try:
                new_page.close()
            except PlaywrightError:
                pass

        context.on("page", close_popup)
        try:
            page.goto(GOOGLE_FORM_URL, wait_until="domcontentloaded", timeout=20_000)
            report.final_url = _safe_report_url(page.url)
            parsed_final = urlsplit(page.url)
            if parsed_final.scheme != "https" or parsed_final.hostname != "support.google.com":
                report.notes.append("The page did not remain on the expected official support.google.com host.")
                return report

            report.verification_challenge_detected = _verification_challenge_visible(page)
            if human_handoff:
                _perform_human_handoff(page, report, prompt_fn)
                return report

            # CAPTCHA is a hard stop in automatic mode. Do not interact with
            # the form wizard if verification is already visible.
            if not _safe_to_inspect_without_handoff(page):
                report.visible_fields, report.visible_buttons = _visible_field_metadata(page)
                report.notes.append(
                    "CAPTCHA/human verification was visible before branch selection. "
                    "Stopped without interacting further; rerun with --headed --human-handoff "
                    "for guarded manual observation."
                )
                return report

            first_branch = EXPECTED_CONTACT_STEPS[0]
            if _click_unique_visible_text(page, first_branch):
                report.selected_steps.append(first_branch)
            else:
                report.notes.append(
                    "Could not identify exactly one visible control for the personal-information branch. "
                    "Stopped without entering data."
                )
                report.visible_fields, report.visible_buttons = _visible_field_metadata(page)
                return report

            contact_branch = EXPECTED_CONTACT_STEPS[1]
            if _click_unique_visible_text(page, contact_branch):
                report.selected_steps.append(contact_branch)
            else:
                report.notes.append(
                    "Could not identify exactly one visible contact-info option. "
                    "Stopped without entering data."
                )

            # Inspect only. Never fill fields, click Next, or click Submit.
            page.wait_for_timeout(350)
            report.final_url = _safe_report_url(page.url)
            report.visible_fields, report.visible_buttons = _visible_field_metadata(page)
            report.notes.append("Read-only inspection: no fields were filled and no submit button was clicked.")
            if report.blocked_requests:
                report.notes.append(
                    f"{len(report.blocked_requests)} request(s) were blocked by the read-only guard."
                )
            return report
        except EOFError:
            report.final_url = _safe_report_url(page.url)
            report.notes.append(
                "Human handoff ended before operator confirmation. No fields were filled and nothing was submitted."
            )
            return report
        except PlaywrightError as exc:
            # Diagnostics deliberately exclude page content, cookies, and input values.
            report.notes.append(f"Browser inspection stopped safely: {type(exc).__name__}.")
            report.final_url = _safe_report_url(page.url)
            return report
        finally:
            context.close()
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect Google's public contact-info Search-removal form without submitting."
    )
    parser.add_argument("--headed", action="store_true", help="Show the browser window while inspecting.")
    parser.add_argument(
        "--human-handoff",
        action="store_true",
        help="Pause for manual observation while the strict read-only network guard remains active.",
    )
    args = parser.parse_args()
    if args.human_handoff and not args.headed:
        parser.error("--human-handoff requires --headed")
    if args.human_handoff and not sys.stdin.isatty():
        parser.error("--human-handoff requires an interactive terminal")

    report = inspect_google_contact_form(
        headless=not args.headed,
        human_handoff=args.human_handoff,
    )
    print(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    if report.selected_steps != EXPECTED_CONTACT_STEPS:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
