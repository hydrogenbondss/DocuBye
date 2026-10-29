"""Bounded Playwright runner for the synthetic removal workflow."""

from __future__ import annotations

import ipaddress
import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from .models import SyntheticProfile, TaskRecord, TaskStatus
from .planner import FieldPlanner, FormField, RuleBasedPlanner

ALLOWED_FORM_FIELDS = {"full_name", "email", "phone", "confirm_own_data"}
ALLOWED_INPUT_TYPES = {"text", "email", "tel", "checkbox"}
ALLOWED_ENDPOINTS = {
    ("GET", "/"): None,
    ("GET", "/opt-out"): None,
    ("GET", "/verify"): None,
    ("GET", "/favicon.ico"): None,
    ("POST", "/submit"): "approval-gated",
}


@dataclass(frozen=True, slots=True)
class ReviewSummary:
    destination: str
    data_categories: tuple[str, ...]
    source_is_local_fixture: bool = True


@dataclass(slots=True)
class RunResult:
    task: TaskRecord
    message: str
    blocked_hosts: list[str]
    review: ReviewSummary | None = None
    blocked_submission_attempts: int = 0
    blocked_requests: list[str] = field(default_factory=list)


def validate_local_base_url(base_url: str) -> str:
    """Only accept the exact IPv4 loopback host and an explicit port."""
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("The first milestone only permits plain HTTP to 127.0.0.1")
    try:
        host_ip = ipaddress.ip_address(parsed.hostname)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("The first milestone only permits an IPv4 loopback URL at 127.0.0.1 with an explicit port") from exc
    if host_ip != ipaddress.IPv4Address("127.0.0.1"):
        raise ValueError("Only the mock site's exact loopback host 127.0.0.1 is permitted")
    if port is None:
        raise ValueError("The local mock URL must include its explicit port")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Pass only the mock site's origin, without a path or query")
    return f"http://127.0.0.1:{port}"


class MockRemovalAgent:
    """Runs against the local fixture only; all requests are checked by the controller."""

    def __init__(self, planner: FieldPlanner | None = None, headless: bool = True) -> None:
        self.planner = planner or RuleBasedPlanner()
        self.headless = headless

    def run(
        self,
        base_url: str,
        profile: SyntheticProfile,
        approval_callback: Callable[[ReviewSummary], bool | None],
    ) -> RunResult:
        if profile != SyntheticProfile():
            raise ValueError(
                "This prototype accepts only its fixed synthetic profile; real personal data is not supported"
            )
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install dependencies with: pip install -e '.[dev]'") from exc

        origin = validate_local_base_url(base_url)
        task = TaskRecord()
        blocked_hosts: list[str] = []
        blocked_requests: list[str] = []
        submission_approved = False
        submission_consumed = False
        submission_forwarded = False
        expected_submission_payload: dict[str, list[str]] = {}
        blocked_submission_count = 0
        page = None

        def make_result(message: str, review: ReviewSummary | None = None) -> RunResult:
            return RunResult(
                task=task,
                message=message,
                blocked_hosts=list(blocked_hosts),
                review=review,
                blocked_submission_attempts=blocked_submission_count,
                blocked_requests=list(blocked_requests),
            )

        def deny(route, detail: str, count_submission: bool = False) -> None:
            nonlocal blocked_submission_count
            if count_submission:
                blocked_submission_count += 1
            blocked_requests.append(detail[:160])
            route.fulfill(status=403, body="Blocked by DocuBye local test guard")

        def guard(route) -> None:
            nonlocal blocked_submission_count, submission_approved
            nonlocal submission_consumed, submission_forwarded
            request = route.request
            parsed = urlsplit(request.url)
            request_origin = f"{parsed.scheme}://{parsed.netloc}"
            method = request.method.upper()
            path = parsed.path

            if request_origin != origin or parsed.scheme != "http":
                blocked_hosts.append(parsed.hostname or "<invalid-url>")
                blocked_requests.append(f"EXTERNAL {method} {parsed.hostname or '<invalid-url>'}"[:160])
                route.abort("blockedbyclient")
                return

            if parsed.query or (method, path) not in ALLOWED_ENDPOINTS:
                deny(route, f"UNEXPECTED {method} {path}", count_submission=(path == "/submit" and method == "POST"))
                return

            if path == "/submit" and method == "POST":
                if not submission_approved or submission_consumed:
                    deny(route, "POST /submit (no active one-time approval)", count_submission=True)
                    return

                # Any attempt consumes the one-time approval, even if its frame or payload is invalid.
                # This prevents a bad first request from leaving the approval token reusable.
                submission_approved = False
                submission_consumed = True
                try:
                    is_main_frame = page is not None and request.frame == page.main_frame
                except PlaywrightError:
                    is_main_frame = False
                if request.resource_type != "document" or not is_main_frame:
                    deny(route, "POST /submit (not a main-frame document submission)", count_submission=True)
                    return
                try:
                    actual_payload = parse_qs(request.post_data or "", keep_blank_values=True, strict_parsing=True)
                except ValueError:
                    actual_payload = {}
                if not expected_submission_payload or actual_payload != expected_submission_payload:
                    deny(route, "POST /submit (payload differs from reviewed form)", count_submission=True)
                    return

                submission_forwarded = True
                route.continue_()
                return

            route.continue_()

        def block_websocket(websocket_route) -> None:
            parsed_socket = urlsplit(websocket_route.url)
            host = parsed_socket.hostname or "<invalid-url>"
            blocked_hosts.append(host)
            blocked_requests.append(f"WEBSOCKET {host}"[:160])
            # Do not call connect_to_server(): Playwright keeps this socket mocked,
            # so page messages are handled locally and never forwarded externally.
            websocket_route.on_message(lambda _message: None)

        with sync_playwright() as playwright:
            executable_path = os.getenv("DOCUBYE_CHROMIUM_EXECUTABLE") or None
            browser = playwright.chromium.launch(headless=self.headless, executable_path=executable_path)
            context = browser.new_context(service_workers="block")
            context.route("**/*", guard)
            context.route_web_socket(lambda url: True, block_websocket)
            page = context.new_page()
            page.set_default_timeout(5_000)
            try:
                page.goto(f"{origin}/opt-out", wait_until="domcontentloaded")
                # Allow immediate page scripts, popups, and frame loads to hit the request guard.
                page.wait_for_timeout(100)
                if blocked_hosts or blocked_requests:
                    if task.status is TaskStatus.DISCOVERED:
                        task.transition(TaskStatus.AWAITING_USER, "Blocked navigation or request needs human review")
                    return make_result(
                        "The page attempted an external or unsupported request. It was blocked; review is required."
                    )

                if page.locator('[data-testid="human-check"]').count():
                    task.transition(TaskStatus.AWAITING_USER, "Human verification required")
                    return make_result("The site requires human verification; no submission was made.")
                if page.locator('[data-testid="unexpected-step"]').count():
                    task.transition(TaskStatus.AWAITING_USER, "Unexpected request requires review")
                    return make_result("The site requested an out-of-scope action; no submission was made.")

                form = page.locator("#opt-out-form")
                if page.locator("form").count() != 1 or form.count() != 1:
                    task.transition(TaskStatus.AWAITING_USER, "Form structure requires human review")
                    return make_result("The page did not contain exactly one expected form; no submission was made.")

                form_config = form.evaluate(
                    "(el) => ({action: el.action, method: el.method.toUpperCase()})"
                )
                submit_button = page.get_by_role("button", name="Submit opt-out request", exact=True)
                if submit_button.count() != 1:
                    task.transition(TaskStatus.AWAITING_USER, "Submit control requires human review")
                    return make_result("The expected submit control was missing or ambiguous; no submission was made.")
                button_config = submit_button.evaluate(
                    "(el) => ({"
                    "action: el.hasAttribute('formaction') ? el.formAction : el.form.action, "
                    "method: el.hasAttribute('formmethod') ? el.formMethod.toUpperCase() : el.form.method.toUpperCase()"
                    "})"
                )
                expected_action = f"{origin}/submit"
                if (
                    form_config != {"action": expected_action, "method": "POST"}
                    or button_config != {"action": expected_action, "method": "POST"}
                ):
                    task.transition(TaskStatus.AWAITING_USER, "Form destination or method differs from the expected flow")
                    return make_result("The form destination or submission method was unexpected; no submission was made.")

                field_records = form.locator("input").evaluate_all(
                    "elements => elements.map(el => ({"
                    "name: el.name, type: el.type, required: !!el.required, "
                    "label: el.labels && el.labels.length ? Array.from(el.labels).map(x => x.textContent.trim()).join(' ') : ''"
                    "}))"
                )
                fields = [
                    FormField(
                        name=str(item["name"]),
                        label=str(item["label"]),
                        input_type=str(item["type"]),
                        required=bool(item["required"]),
                    )
                    for item in field_records
                ]
                field_names = [item.name for item in fields]
                if (
                    not fields
                    or len(field_names) != len(set(field_names))
                    or any(
                        not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", item.name)
                        or item.name not in ALLOWED_FORM_FIELDS
                        or item.input_type not in ALLOWED_INPUT_TYPES
                        for item in fields
                    )
                ):
                    task.transition(TaskStatus.AWAITING_USER, "Unexpected form schema requires review")
                    return make_result("The form contains duplicate or unsupported fields; no submission was made.")

                plannable_fields = [item for item in fields if item.name != "confirm_own_data"]
                try:
                    mapping_plan = self.planner.map_fields(plannable_fields)
                except Exception:
                    task.transition(TaskStatus.FAILED, "Field planner failed safely")
                    return make_result("Field planning failed; no submission was made.")
                if mapping_plan.needs_human_help:
                    task.transition(TaskStatus.AWAITING_USER, "Field mapping requires human review")
                    return make_result(mapping_plan.reason or "Field mapping needs review.")

                values = profile.values()
                required_fields = {item.name for item in plannable_fields if item.required}
                if not required_fields.issubset(mapping_plan.mapping.keys()):
                    task.transition(TaskStatus.AWAITING_USER, "Required field mapping is incomplete")
                    return make_result("The planner did not map every required field; no submission was made.")

                for input_name, profile_field in mapping_plan.mapping.items():
                    if profile_field not in values or not values[profile_field]:
                        task.transition(TaskStatus.AWAITING_USER, "Mapped profile value is unavailable")
                        return make_result("A required profile value is unavailable; no submission was made.")
                    page.locator(f'input[name="{input_name}"]').fill(values[profile_field])

                if "confirm_own_data" not in field_names:
                    task.transition(TaskStatus.AWAITING_USER, "Required attestation missing")
                    return make_result("The expected own-data confirmation is missing; no submission was made.")
                page.locator('input[name="confirm_own_data"]').check()

                # Snapshot the exact form payload before asking for approval. Keep it in memory only.
                form_entries = form.evaluate(
                    "(el) => Array.from(new FormData(el).entries()).map(([name, value]) => [name, String(value)])"
                )
                expected_submission_payload = {}
                for name, value in form_entries:
                    if name in expected_submission_payload:
                        task.transition(TaskStatus.AWAITING_USER, "Duplicate form values require review")
                        return make_result("The form submitted duplicate field names; no submission was made.")
                    expected_submission_payload[name] = [value]
                if set(expected_submission_payload) != {"full_name", "email", "phone", "confirm_own_data"}:
                    task.transition(TaskStatus.AWAITING_USER, "Form payload differs from allowed schema")
                    return make_result("The form payload contained missing or unexpected fields; no submission was made.")

                review = ReviewSummary(
                    destination=f"{origin}/submit",
                    data_categories=tuple(
                        canonical for canonical in ("full_name", "email", "phone")
                        if canonical in mapping_plan.mapping.values()
                    ),
                )
                task.transition(TaskStatus.READY_FOR_REVIEW, "Form mapped; review prepared")
                decision = approval_callback(review)
                if decision is None:
                    task.transition(TaskStatus.AWAITING_USER, "Waiting for explicit approval")
                    return make_result("Waiting for the user; no submission was made.", review)
                if decision is not True:
                    task.transition(TaskStatus.REJECTED, "User rejected submission")
                    return make_result("The user rejected the submission; nothing was sent.", review)

                task.begin_submission()
                submission_approved = True
                try:
                    submit_button.click()
                    page.get_by_test_id("submitted").wait_for(state="visible")
                except PlaywrightError:
                    if not submission_forwarded and blocked_submission_count > 0:
                        task.transition(TaskStatus.FAILED, "Submission blocked before reaching the mock endpoint")
                        return make_result(
                            "The proposed submission was blocked because it did not match the reviewed request. Nothing was sent; automatic retry is disabled.",
                            review,
                        )
                    if not submission_forwarded:
                        task.transition(TaskStatus.UNKNOWN, "Submission could not be safely resolved; retry disabled")
                        return make_result(
                            "Submission status is unknown; no automatic retry will occur.",
                            review,
                        )
                    task.transition(TaskStatus.UNKNOWN, "Submission outcome could not be confirmed")
                    return make_result("Submission outcome is unknown; automatic retry is disabled.", review)

                task.transition(TaskStatus.SUBMITTED, "Mock site acknowledged submission")
                task.transition(TaskStatus.AWAITING_CONFIRMATION, "Awaiting separate removal verification")
                page.goto(f"{origin}/verify", wait_until="domcontentloaded")
                verification = page.get_by_test_id("verification-result").inner_text().strip().casefold()
                if verification == "removal verified":
                    task.transition(TaskStatus.VERIFIED_REMOVED, "Mock verification endpoint confirmed removal")
                    message = "The mock verification endpoint confirmed removal. This is simulated test evidence only."
                else:
                    message = "The request was submitted, but removal is not verified."
                return make_result(message, review)
            except PlaywrightError:
                if blocked_hosts or blocked_requests:
                    if task.status in {TaskStatus.DISCOVERED, TaskStatus.READY_FOR_REVIEW}:
                        task.transition(TaskStatus.AWAITING_USER, "Blocked navigation or request needs human review")
                    return make_result(
                        "The page attempted an external or unsupported request. It was blocked; review is required."
                    )
                if task.status in {TaskStatus.DISCOVERED, TaskStatus.READY_FOR_REVIEW}:
                    task.transition(TaskStatus.FAILED, "Browser workflow failed before submission")
                elif task.status is TaskStatus.SUBMITTING and not submission_forwarded:
                    task.transition(TaskStatus.UNKNOWN, "Submission could not be resolved; retry disabled")
                elif task.status in {
                    TaskStatus.SUBMITTING, TaskStatus.SUBMITTED, TaskStatus.AWAITING_CONFIRMATION
                }:
                    task.transition(TaskStatus.UNKNOWN, "Submission or verification outcome is unknown; retry disabled")
                return make_result(
                    "The browser workflow failed safely; inspect the task status before retrying."
                )
            finally:
                context.close()
                browser.close()
