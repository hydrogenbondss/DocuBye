import pytest

from docubye.models import TaskRecord, TaskStatus
from docubye.sources.google import (
    DATA_CATEGORIES,
    FORM_PATH,
    REQUIRED_ATTESTATIONS,
    REQUIRED_ATTESTATIONS as ATTESTATIONS,
    inspect_google_dry_run,
)
from docubye.store import TaskStore

pytest.importorskip("playwright")

FIXTURE_DIR = "tests/fixtures/google"


def inspect(scenario, store=None, **kwargs):
    return inspect_google_dry_run(
        store=store, fixture_dir=FIXTURE_DIR, scenario=scenario, headless=True, **kwargs
    )


def test_happy_path_produces_a_dry_run_plan_and_never_submits(chromium, tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    outcome = inspect("happy", store=store)

    assert outcome.task.status is TaskStatus.READY_FOR_REVIEW
    assert "NOT implemented" in outcome.message
    plan = outcome.plan
    assert plan is not None
    assert plan.destination.endswith(FORM_PATH)
    assert plan.data_categories == DATA_CATEGORIES
    assert plan.required_attestations == ATTESTATIONS
    assert plan.submission_implemented is False

    # The submit control is observed but never activated; Next is documented too.
    assert "Submit" in plan.visible_buttons
    assert "Next" in plan.visible_buttons

    # Field metadata was collected without values.
    names = {f.name for f in plan.visible_fields}
    assert {"exposed_value", "content_url", "search_results_url", "contact_email"} <= names
    assert all(not hasattr(f, "value") for f in plan.visible_fields)

    # The planner refuses to guess: the M1 profile schema does not fit these
    # fields, so required fields stay unmapped for human review.
    assert plan.field_mapping.needs_human_help
    assert "exposed_value" in plan.unmapped_required_fields
    assert "contact_email" in plan.unmapped_required_fields

    # Human-only attestations are named, never asserted by the adapter.
    assert any("accuracy" in item for item in REQUIRED_ATTESTATIONS)
    assert any("authority" in item for item in REQUIRED_ATTESTATIONS)

    # State machine and store integration: history persisted, honest statuses only.
    statuses = [event.status for event in outcome.task.events]
    assert statuses == ["discovered", "ready_for_review"]
    reloaded = TaskStore(tmp_path / "tasks.sqlite3").load_task(outcome.task.task_id)
    assert [e.detail for e in reloaded.task.events] == [e.detail for e in outcome.task.events]


def test_login_wall_pauses_for_a_human(chromium):
    outcome = inspect("login-wall")
    assert outcome.task.status is TaskStatus.AWAITING_USER
    assert outcome.plan is None
    assert any("Sign-in wall" in event.detail for event in outcome.task.events)


def test_visible_captcha_pauses_for_a_human(chromium):
    outcome = inspect("captcha")
    assert outcome.task.status is TaskStatus.AWAITING_USER
    assert outcome.plan is None
    assert any("verification challenge" in event.detail for event in outcome.task.events)


def test_unexpected_page_structure_pauses_without_guessing(chromium):
    outcome = inspect("unexpected")
    assert outcome.task.status is TaskStatus.AWAITING_USER
    assert outcome.plan is None
    assert any("requires review" in event.detail for event in outcome.task.events)


def test_mutated_form_destination_pauses(chromium):
    outcome = inspect("mutated-action")
    assert outcome.task.status is TaskStatus.AWAITING_USER
    assert outcome.plan is None
    assert any("destination" in event.detail for event in outcome.task.events)


def test_prompt_injection_text_is_ignored(chromium):
    outcome = inspect("injection")
    assert outcome.task.status is TaskStatus.READY_FOR_REVIEW
    assert outcome.plan is not None
    assert outcome.blocked_requests == []


def test_page_initiated_post_is_blocked_and_never_reaches_the_server(chromium):
    outcome = inspect("post-attack")
    assert outcome.task.status is TaskStatus.AWAITING_USER
    assert outcome.plan is None
    assert any(req["method"] == "POST" for req in outcome.blocked_requests)
    # Redacted logging: only method/host/path, never a body.
    assert set(outcome.blocked_requests[0]) == {"method", "host", "path"}
    assert any("Blocked navigation" in event.detail for event in outcome.task.events)


def test_live_mode_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("DOCUBYE_REAL_SOURCE", raising=False)
    with pytest.raises(RuntimeError, match="DOCUBYE_REAL_SOURCE"):
        inspect_google_dry_run(fixture_dir=None)


def test_inspection_refuses_a_task_that_is_not_discovered(chromium):
    task = TaskRecord()
    task.transition(TaskStatus.READY_FOR_REVIEW, "review prepared")
    with pytest.raises(ValueError, match="Only a DISCOVERED task"):
        inspect_google_dry_run(fixture_dir=FIXTURE_DIR, task=task)


def test_plan_and_events_contain_no_personal_values(chromium, tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    outcome = inspect("happy", store=store)
    blob = repr(outcome.plan) + repr(outcome.task.to_public_dict())
    for forbidden in ("alex", "@example", "555 0147", "cookie"):
        assert forbidden not in blob.casefold()


def test_unknown_scenario_is_rejected():
    with pytest.raises(ValueError, match="Unsupported Google fixture scenario"):
        inspect_google_dry_run(fixture_dir=FIXTURE_DIR, scenario="production")
