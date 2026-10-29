"""Read-only inspection of Google's public personal-contact removal form.

This command never fills fields or submits a report. It uses a fresh browser
context, blocks all non-GET requests, blocks unapproved hosts, and never opens
a WebSocket connection to a server.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit

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
BLOCKED_PATH_RE = re.compile(r"/(?:submit|formresponse|sendreport)(?:/|$)", re.IGNORECASE)


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
    submitted: bool = False
    filled_fields: bool = False
    notes: list[str] = field(default_factory=list)


def inspection_request_allowed(url: str, method: str) -> bool:
    """Read-only network policy helper, tested without network access."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme != "https" or host not in ALLOWED_READ_HOSTS:
        return False
    if host in BLOCKED_HOSTS or method.upper() not in {"GET", "HEAD"}:
        return False
    if BLOCKED_PATH_RE.search(parsed.path):
        return False
    return True


def websocket_inspection_allowed(_url: str) -> bool:
    """The inspector never opens or forwards WebSocket connections."""
    return False


def _verification_challenge_visible(page) -> bool:
    """Return true when a visible CAPTCHA/human-verification element is present."""
    return bool(page.locator(
        'iframe[src*="recaptcha"], iframe[title*="challenge" i], '
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
    """The form wizard must stop before interaction if verification is visible."""
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


def inspect_google_contact_form(*, headless: bool = True) -> InspectionReport:
    """Inspect visible branch labels and field metadata without entering any data."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Install dependencies with: pip install -e '.[dev]'") from exc

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
        context = browser.new_context(service_workers="block")
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
            report.final_url = page.url
            parsed_final = urlsplit(page.url)
            if parsed_final.scheme != "https" or parsed_final.hostname != "support.google.com":
                report.notes.append("The page did not remain on the expected official support.google.com host.")
                return report

            # CAPTCHA is a hard handoff. Do not interact with the form wizard
            # if verification is already visible, even to select a branch.
            if not _safe_to_inspect_without_handoff(page):
                report.verification_challenge_detected = True
                report.visible_fields, report.visible_buttons = _visible_field_metadata(page)
                report.notes.append(
                    "CAPTCHA/human verification was visible before branch selection. "
                    "Stopped without interacting further; a person must take over."
                )
                return report

            first_branch = "Content contains your personal information"
            if _click_unique_visible_text(page, first_branch):
                report.selected_steps.append(first_branch)
            else:
                report.notes.append(
                    "Could not identify exactly one visible control for the personal-information branch. "
                    "Stopped without entering data."
                )
                report.visible_fields, report.visible_buttons = _visible_field_metadata(page)
                return report

            contact_branch = "Address, phone number, and/or e-mail address"
            if _click_unique_visible_text(page, contact_branch):
                report.selected_steps.append(contact_branch)
            else:
                report.notes.append(
                    "Could not identify exactly one visible contact-info option. "
                    "Stopped without entering data."
                )

            # Inspect only. Never fill fields, click Next, or click Submit.
            page.wait_for_timeout(350)
            report.final_url = page.url
            report.visible_fields, report.visible_buttons = _visible_field_metadata(page)
            report.notes.append("Read-only inspection: no fields were filled and no submit button was clicked.")
            if any(item["method"] not in {"GET", "HEAD"} for item in report.blocked_requests):
                report.notes.append("One or more non-read requests were blocked by the guard.")
            return report
        except PlaywrightError as exc:
            # Diagnostics deliberately exclude page content, cookies, and input values.
            report.notes.append(f"Browser inspection stopped safely: {type(exc).__name__}.")
            report.final_url = page.url
            return report
        finally:
            context.close()
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect Google's public contact-info Search-removal form without submitting."
    )
    parser.add_argument("--headed", action="store_true", help="Show the browser window while inspecting.")
    args = parser.parse_args()
    report = inspect_google_contact_form(headless=not args.headed)
    print(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    if report.selected_steps != [
        "Content contains your personal information",
        "Address, phone number, and/or e-mail address",
    ]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
