"""Bounded Playwright runner for the synthetic removal workflow."""

from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

from .models import SyntheticProfile, TaskRecord, TaskStatus
from .planner import FieldPlanner, FormField, RuleBasedPlanner

ALLOWED_FORM_FIELDS = {"full_name", "email", "phone", "confirm_own_data"}
ALLOWED_INPUT_TYPES = {"text", "email", "tel", "checkbox"}


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


def validate_local_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("The first milestone only permits plain HTTP to a loopback host")
    try:
        loopback = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        raise ValueError("External hosts are forbidden in the synthetic browser workflow")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Pass only the mock site's origin, without a path or query")
    return f"http://{parsed.netloc}"


class MockRemovalAgent:
    """Runs against the local fixture only; every navigation is guarded."""

    def __init__(self, planner: FieldPlanner | None = None, headless: bool = True) -> None:
        self.planner = planner or RuleBasedPlanner()
        self.headless = headless

    def run(self, base_url: str, profile: SyntheticProfile,
            approval_callback: Callable[[ReviewSummary], bool | None]) -> RunResult:
        if profile != SyntheticProfile():
            raise ValueError("This prototype accepts only its fixed synthetic profile; real personal data is not supported")
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install dependencies with: pip install -e '.[dev]'") from exc

        origin = validate_local_base_url(base_url)
        task = TaskRecord()
        blocked_hosts: list[str] = []
        submission_approved = False
        blocked_submission_count = 0

        def guard(route) -> None:
            nonlocal blocked_submission_count
            parsed = urlsplit(route.request.url)
            request_origin = f"{parsed.scheme}://{parsed.netloc}"
            if request_origin != origin or parsed.scheme != "http":
                blocked_hosts.append(parsed.hostname or "<invalid-url>")
                route.abort("blockedbyclient")
                return
            if parsed.path == "/submit" and route.request.method.upper() == "POST" and not submission_approved:
                blocked_submission_count += 1
                route.fulfill(status=403, body="Submission blocked: approval required")
                return
            route.continue_()

        with sync_playwright() as playwright:
            executable_path = os.getenv("DOCUBYE_CHROMIUM_EXECUTABLE") or None
            browser = playwright.chromium.launch(headless=self.headless, executable_path=executable_path)
            context = browser.new_context(service_workers="block")
            context.route("**/*", guard)
            page = context.new_page()
            page.set_default_timeout(5_000)
            try:
                page.goto(f"{origin}/opt-out", wait_until="domcontentloaded")
                if page.locator('[data-testid="human-check"]').count():
                    task.transition(TaskStatus.AWAITING_USER, "Human verification required")
                    return RunResult(task, "The site requires human verification; no submission was made.", blocked_hosts)
                if page.locator('[data-testid="unexpected-step"]').count():
                    task.transition(TaskStatus.AWAITING_USER, "Unexpected request requires review")
                    return RunResult(task, "The site requested an out-of-scope action; no submission was made.", blocked_hosts)

                field_records = page.locator("#opt-out-form input").evaluate_all(
                    "elements => elements.map(el => ({"
                    "name: el.name, type: el.type, required: !!el.required, "
                    "label: el.labels && el.labels.length ? Array.from(el.labels).map(x => x.textContent.trim()).join(' ') : ''"
                    "}))"
                )
                fields = [
                    FormField(name=str(item["name"]), label=str(item["label"]),
                              input_type=str(item["type"]), required=bool(item["required"]))
                    for item in field_records
                ]
                if not fields or any(
                    not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", item.name)
                    or item.name not in ALLOWED_FORM_FIELDS
                    or item.input_type not in ALLOWED_INPUT_TYPES
                    for item in fields
                ):
                    task.transition(TaskStatus.AWAITING_USER, "Unexpected form schema requires review")
                    return RunResult(task, "The form contains an unsupported field; no submission was made.", blocked_hosts)

                plannable_fields = [item for item in fields if item.name != "confirm_own_data"]
                try:
                    mapping_plan = self.planner.map_fields(plannable_fields)
                except Exception:
                    task.transition(TaskStatus.FAILED, "Field planner failed safely")
                    return RunResult(task, "Field planning failed; no submission was made.", blocked_hosts,
                                     blocked_submission_attempts=blocked_submission_count)
                if mapping_plan.needs_human_help:
                    task.transition(TaskStatus.AWAITING_USER, "Field mapping requires human review")
                    return RunResult(task, mapping_plan.reason or "Field mapping needs review.", blocked_hosts)

                values = profile.values()
                required_fields = {item.name for item in plannable_fields if item.required}
                if not required_fields.issubset(mapping_plan.mapping.keys()):
                    task.transition(TaskStatus.AWAITING_USER, "Required field mapping is incomplete")
                    return RunResult(task, "The planner did not map every required field; no submission was made.", blocked_hosts)

                for input_name, profile_field in mapping_plan.mapping.items():
                    if profile_field not in values or not values[profile_field]:
                        task.transition(TaskStatus.AWAITING_USER, "Mapped profile value is unavailable")
                        return RunResult(task, "A required profile value is unavailable; no submission was made.", blocked_hosts)
                    page.locator(f'input[name="{input_name}"]').fill(values[profile_field])

                if "confirm_own_data" not in {item.name for item in fields}:
                    task.transition(TaskStatus.AWAITING_USER, "Required attestation missing")
                    return RunResult(task, "The expected own-data confirmation is missing; no submission was made.", blocked_hosts)
                page.locator('input[name="confirm_own_data"]').check()

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
                    return RunResult(task, "Waiting for the user; no submission was made.", blocked_hosts,
                                     review, blocked_submission_count)
                if decision is not True:
                    task.transition(TaskStatus.REJECTED, "User rejected submission")
                    return RunResult(task, "The user rejected the submission; nothing was sent.", blocked_hosts,
                                     review, blocked_submission_count)

                task.begin_submission()
                submission_approved = True
                try:
                    page.get_by_role("button", name="Submit opt-out request", exact=True).click()
                    page.get_by_test_id("submitted").wait_for(state="visible")
                except PlaywrightError:
                    task.transition(TaskStatus.UNKNOWN, "Submission outcome could not be confirmed")
                    return RunResult(task, "Submission outcome is unknown; automatic retry is disabled.",
                                     blocked_hosts, review, blocked_submission_count)

                task.transition(TaskStatus.SUBMITTED, "Mock site acknowledged submission")
                task.transition(TaskStatus.AWAITING_CONFIRMATION, "Awaiting separate removal verification")
                page.goto(f"{origin}/verify", wait_until="domcontentloaded")
                verification = page.get_by_test_id("verification-result").inner_text().strip().casefold()
                if verification == "removal verified":
                    task.transition(TaskStatus.VERIFIED_REMOVED, "Mock verification endpoint confirmed removal")
                    message = "The mock verification endpoint confirmed removal. This is simulated test evidence only."
                else:
                    message = "The request was submitted, but removal is not verified."
                return RunResult(task, message, blocked_hosts, review, blocked_submission_count)
            except PlaywrightError as exc:
                if os.getenv("DOCUBYE_CHROMIUM_EXECUTABLE") and "ERR_BLOCKED_BY_ADMINISTRATOR" in str(exc):
                    raise
                if task.status in {TaskStatus.DISCOVERED, TaskStatus.READY_FOR_REVIEW}:
                    task.transition(TaskStatus.FAILED, "Browser workflow failed before submission")
                elif task.status in {TaskStatus.SUBMITTING, TaskStatus.SUBMITTED, TaskStatus.AWAITING_CONFIRMATION}:
                    task.transition(TaskStatus.UNKNOWN, "Submission or verification outcome is unknown; retry disabled")
                return RunResult(task, "The browser workflow failed safely; inspect the task status before retrying.",
                                 blocked_hosts, blocked_submission_attempts=blocked_submission_count)
            finally:
                context.close()
                browser.close()
