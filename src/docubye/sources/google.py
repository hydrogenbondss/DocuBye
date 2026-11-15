"""Read-only Google contact-removal source adapter (dry-run only).

This module navigates the documented public wizard from
docs/FIRST_SOURCE_REVIEW.md, collects visible field metadata, and produces a
dry-run plan for human review. Submission is NOT implemented: no code path
here fills a field, clicks a submit control, or sends a request body. Every
POST/PUT/PATCH/DELETE is blocked by the route guard and recorded redacted
(method, host, path only).

Live navigation requires the explicit DOCUBYE_REAL_SOURCE=1 opt-in. Without a
fixture directory the adapter refuses to touch the network. Tests and CI run
against the sanitized snapshots in tests/fixtures/google/.
"""

from __future__ import annotations

import argparse
import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from ..google_inspect import (
    EXPECTED_CONTACT_STEPS,
    VisibleField,
    _click_unique_visible_text,
    _verification_challenge_visible,
    _visible_field_metadata,
    inspection_request_allowed,
)
from ..models import TaskRecord, TaskStatus
from ..planner import FormField, MappingPlan, RuleBasedPlanner
from ..store import TaskStore

FORM_PATH = "/websearch/contact/content_removal_form"
LIVE_FORM_URL = f"https://support.google.com{FORM_PATH}?hl=en"
REAL_SOURCE_ENV = "DOCUBYE_REAL_SOURCE"

FIXTURE_SCENARIOS = {
    "happy", "login-wall", "captcha", "unexpected", "mutated-action", "post-attack", "injection",
}

DATA_CATEGORIES = (
    "exposed contact value",
    "content URLs",
    "search results URLs",
    "search terms",
    "country of residence",
    "contact email",
)
REQUIRED_ATTESTATIONS = (
    "accuracy of the request (human attestation only)",
    "authority to act for the person concerned (human attestation only)",
    "scope acknowledgement: search-result delisting, not source deletion (human only)",
)

DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "google"


@dataclass(frozen=True, slots=True)
class DryRunPlan:
    """What a real request WOULD contain. Never values, never a submission."""

    destination: str
    data_categories: tuple[str, ...]
    required_attestations: tuple[str, ...]
    visible_fields: tuple[VisibleField, ...]
    visible_buttons: tuple[str, ...]
    field_mapping: MappingPlan
    unmapped_required_fields: tuple[str, ...]
    submission_implemented: bool = False


@dataclass(slots=True)
class InspectionOutcome:
    task: TaskRecord
    message: str
    plan: DryRunPlan | None = None
    blocked_requests: list[dict[str, str]] = field(default_factory=list)


@contextmanager
def serve_google_fixtures(fixture_dir: str | Path, scenario: str = "happy"):
    """Serve one sanitized snapshot at the documented form path on 127.0.0.1."""
    if scenario not in FIXTURE_SCENARIOS:
        raise ValueError(f"Unsupported Google fixture scenario: {scenario}")
    body = (Path(fixture_dir) / f"{scenario}.html").read_text(encoding="utf-8")
    counts = {"posts": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            if urlsplit(self.path).path == FORM_PATH:
                payload = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            # A correct adapter never sends these; count to prove that in tests.
            counts["posts"] += 1
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}", counts
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _login_wall_visible(page) -> bool:
    """Detect a sign-in wall without reading any input values."""
    host = (urlsplit(page.url).hostname or "").casefold()
    if host.startswith("accounts.google."):
        return True
    return bool(page.locator(
        "h1, h2, p"
    ).evaluate_all(
        """elements => elements.some(el => {
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            const visible = !el.hidden && style.display !== 'none' && style.visibility !== 'hidden'
                && rect.width > 0 && rect.height > 0;
            return visible && /sign in to continue/i.test(el.textContent || '');
        })"""
    ))


def _pause(task: TaskRecord, detail: str, message: str) -> InspectionOutcome:
    task.transition(TaskStatus.AWAITING_USER, detail)
    return InspectionOutcome(task=task, message=message)


def inspect_google_dry_run(
    *,
    store: TaskStore | None = None,
    task: TaskRecord | None = None,
    fixture_dir: str | Path | None = DEFAULT_FIXTURE_DIR,
    scenario: str = "happy",
    headless: bool = True,
) -> InspectionOutcome:
    """Inspect the documented Google flow and produce a dry-run plan.

    Fixture mode (default) serves sanitized snapshots locally. Pass
    fixture_dir=None for the live site, which requires DOCUBYE_REAL_SOURCE=1.
    """
    live = fixture_dir is None
    if live and os.getenv(REAL_SOURCE_ENV) != "1":
        raise RuntimeError(
            f"Live Google inspection is disabled. Set {REAL_SOURCE_ENV}=1 to opt in explicitly; "
            "tests and CI must use the recorded fixtures."
        )

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install dependencies with: pip install -e '.[dev]'") from exc

    if task is None:
        task = TaskRecord()
    elif task.status is not TaskStatus.DISCOVERED:
        raise ValueError(f"Only a DISCOVERED task can start an inspection; this task is {task.status.value}")
    if store is not None:
        task.add_listener(store.save_task)
        store.save_task(task)

    blocked_requests: list[dict[str, str]] = []

    def record_blocked(method: str, url: str) -> None:
        parsed = urlsplit(url)
        blocked_requests.append({
            "method": method.upper(),
            "host": parsed.hostname or "<invalid-url>",
            "path": parsed.path[:160],
        })

    @contextmanager
    def _fixture_context():
        if live:
            yield LIVE_FORM_URL, {"posts": 0}
        else:
            with serve_google_fixtures(fixture_dir, scenario) as (base, counts):
                yield f"{base}{FORM_PATH}?hl=en", counts

    with _fixture_context() as (form_url, counts):
        fixture_origin = f"{urlsplit(form_url).scheme}://{urlsplit(form_url).netloc}"

        def guard(route) -> None:
            request = route.request
            parsed = urlsplit(request.url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if live:
                allowed = inspection_request_allowed(request.url, request.method)
            else:
                allowed = origin == fixture_origin and request.method.upper() in {"GET", "HEAD"}
            if not allowed:
                record_blocked(request.method, request.url)
                route.abort("blockedbyclient")
                return
            route.continue_()

        def block_websocket(socket_route) -> None:
            record_blocked("WEBSOCKET", socket_route.url)
            socket_route.on_message(lambda _message: None)

        outcome: InspectionOutcome | None = None
        with sync_playwright() as playwright:
            executable_path = os.getenv("DOCUBYE_CHROMIUM_EXECUTABLE") or None
            browser = playwright.chromium.launch(headless=headless, executable_path=executable_path)
            context = browser.new_context(service_workers="block", accept_downloads=False)
            context.route("**/*", guard)
            context.route_web_socket(lambda _url: True, block_websocket)
            page = context.new_page()
            page.set_default_timeout(6_000)
            try:
                page.goto(form_url, wait_until="domcontentloaded", timeout=20_000)
                page.wait_for_timeout(100)
                if blocked_requests:
                    outcome = _pause(
                        task,
                        "Blocked navigation or request needs human review",
                        "The page attempted an external or non-read-only request. It was blocked; review is required.",
                    )
                    outcome.blocked_requests = blocked_requests

                if outcome is None and _login_wall_visible(page):
                    outcome = _pause(
                        task,
                        "Sign-in wall encountered; no credentials were entered",
                        "The flow requires sign-in. DocuBye does not automate logins; resolve manually.",
                    )
                if outcome is None and _verification_challenge_visible(page):
                    outcome = _pause(
                        task,
                        "Human verification challenge visible",
                        "A CAPTCHA or identity check is visible. DocuBye does not bypass it; resolve manually.",
                    )

                if outcome is None and not _click_unique_visible_text(page, EXPECTED_CONTACT_STEPS[0]):
                    outcome = _pause(
                        task,
                        "Personal-information branch not found; page structure requires review",
                        "The expected branch control was missing or ambiguous; no guessing was attempted.",
                    )
                if outcome is None and not _click_unique_visible_text(page, EXPECTED_CONTACT_STEPS[1]):
                    outcome = _pause(
                        task,
                        "Contact-info sub-branch not found; page structure requires review",
                        "The expected contact-info option was missing or ambiguous; no guessing was attempted.",
                    )
                if outcome is None:
                    page.wait_for_timeout(150)
                    if _verification_challenge_visible(page):
                        outcome = _pause(
                            task,
                            "Human verification challenge visible",
                            "A CAPTCHA or identity check appeared. DocuBye does not bypass it; resolve manually.",
                        )

                if outcome is None:
                    # Destination check: any form or submit control must target the
                    # documented form path on the same origin. A dry run still refuses
                    # to plan against a mutated destination.
                    destinations = page.locator("form").evaluate_all(
                        "elements => elements.map(el => el.action)"
                    ) + page.get_by_role("button", name="Submit", exact=True).evaluate_all(
                        "elements => elements.map(el => el.hasAttribute('formaction') ? el.formAction : el.form.action)"
                    )
                    expected_prefix = f"{urlsplit(form_url).scheme}://{urlsplit(form_url).netloc}{FORM_PATH}"
                    if not destinations or any(not dest.startswith(expected_prefix) for dest in destinations):
                        outcome = _pause(
                            task,
                            "Form destination differs from the documented flow",
                            "The form destination was unexpected; no dry-run plan was produced.",
                        )

                if outcome is None:
                    fields, buttons = _visible_field_metadata(page)
                    plannable = [
                        FormField(name=f.name, label=f.label, input_type=f.field_type, required=f.required)
                        for f in fields
                        if f.tag in {"input", "textarea", "select"} and f.field_type not in {"radio", "checkbox", "file"}
                        and f.name not in {"reason", "info_type", "id_type", "doxxing_intent"}
                    ]
                    mapping = RuleBasedPlanner().map_fields(plannable)
                    mapped_names = set(mapping.mapping)
                    unmapped_required = tuple(
                        f.name for f in plannable if f.required and f.name not in mapped_names
                    )

                    plan = DryRunPlan(
                        destination=f"{urlsplit(form_url).scheme}://{urlsplit(form_url).netloc}{FORM_PATH}",
                        data_categories=DATA_CATEGORIES,
                        required_attestations=REQUIRED_ATTESTATIONS,
                        visible_fields=tuple(fields),
                        visible_buttons=tuple(buttons),
                        field_mapping=mapping,
                        unmapped_required_fields=unmapped_required,
                    )
                    task.transition(
                        TaskStatus.READY_FOR_REVIEW,
                        "Dry-run plan prepared; submission is intentionally not implemented",
                    )
                    outcome = InspectionOutcome(
                        task=task,
                        plan=plan,
                        message=(
                            "Dry-run plan prepared for human review. Submission is NOT implemented; "
                            "the submit control was never activated and no request body was sent."
                        ),
                        blocked_requests=blocked_requests,
                    )
            except PlaywrightError:
                if blocked_requests:
                    outcome = _pause(
                        task,
                        "Blocked navigation or request needs human review",
                        "The page attempted an external or non-read-only request. It was blocked; review is required.",
                    )
                    outcome.blocked_requests = blocked_requests
                else:
                    if task.status is TaskStatus.DISCOVERED:
                        task.transition(TaskStatus.FAILED, "Browser inspection failed before a plan was prepared")
                    outcome = InspectionOutcome(
                        task=task,
                        message="The browser inspection failed safely; inspect the task status before retrying.",
                        blocked_requests=blocked_requests,
                    )
            finally:
                context.close()
                browser.close()

        if counts["posts"]:
            raise AssertionError("The fixture server received a POST; the read-only guard failed")
        outcome.blocked_requests = list(blocked_requests)
        return outcome


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only dry-run inspection of the Google contact-removal flow. Never submits."
    )
    parser.add_argument("--scenario", choices=sorted(FIXTURE_SCENARIOS), default="happy")
    parser.add_argument(
        "--fixture-dir", default=str(DEFAULT_FIXTURE_DIR),
        help="Sanitized snapshot directory (default: tests/fixtures/google). Ignored with --live.",
    )
    parser.add_argument(
        "--live", action="store_true",
        help=f"Inspect the live Google form. Requires {REAL_SOURCE_ENV}=1. Read-only; never submits.",
    )
    parser.add_argument("--store", default="docubye-tasks.sqlite3", help="SQLite task store path")
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    args = parser.parse_args()

    store = TaskStore(args.store)
    try:
        outcome = inspect_google_dry_run(
            store=store,
            fixture_dir=None if args.live else args.fixture_dir,
            scenario=args.scenario,
            headless=not args.headed,
        )
    finally:
        store.close()
    print("\nResult: " + outcome.message)
    print(json.dumps(outcome.task.to_public_dict(), indent=2))
    if outcome.plan is not None:
        plan = asdict(outcome.plan)
        plan["field_mapping"] = {
            "mapping": outcome.plan.field_mapping.mapping,
            "needs_human_help": outcome.plan.field_mapping.needs_human_help,
            "reason": outcome.plan.field_mapping.reason,
        }
        print(json.dumps(plan, indent=2, default=str))
    if outcome.blocked_requests:
        print("Blocked requests (redacted): " + json.dumps(outcome.blocked_requests))


if __name__ == "__main__":
    main()
