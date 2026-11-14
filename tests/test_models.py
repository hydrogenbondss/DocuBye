import json

import pytest

from docubye.models import SyntheticProfile, TaskRecord, TaskStatus, payload_fingerprint_for_payload


def test_task_rejects_invalid_transition():
    task = TaskRecord()
    with pytest.raises(ValueError, match="Invalid task transition"):
        task.transition(TaskStatus.VERIFIED_REMOVED, "must not skip states")


def test_submission_can_only_be_started_once():
    task = TaskRecord()
    task.transition(TaskStatus.READY_FOR_REVIEW, "review prepared")
    task.begin_submission()
    with pytest.raises(ValueError, match="already attempted"):
        task.begin_submission()


def test_public_task_record_does_not_include_profile_values():
    task = TaskRecord()
    payload = task.to_public_dict()
    assert "email" not in payload
    assert "profile" not in payload
    assert payload["status"] == "discovered"


def test_synthetic_profile_loads_from_the_fixture_file():
    from importlib import resources

    fixture = json.loads(
        resources.files("docubye.fixtures").joinpath("synthetic_profile.json").read_text(encoding="utf-8")
    )
    profile = SyntheticProfile()
    assert profile.full_name == fixture["full_name"]
    assert profile.email == fixture["email"]
    assert profile.phone == fixture["phone"]
    assert fixture["email"].endswith(".test")


def test_unknown_can_only_recover_to_awaiting_confirmation():
    task = TaskRecord()
    task.transition(TaskStatus.READY_FOR_REVIEW, "review prepared")
    task.begin_submission()
    task.transition(TaskStatus.UNKNOWN, "submission outcome unresolved")
    with pytest.raises(ValueError, match="Invalid task transition"):
        task.transition(TaskStatus.SUBMITTING, "blind retry stays disabled")
    task.transition(TaskStatus.AWAITING_CONFIRMATION, "original submission found via status lookup")


def test_payload_fingerprint_binds_the_exact_payload():
    payload = {"full_name": "Alex Example", "email": "alex.example@example.test", "phone": "+1 202 555 0147", "confirm_own_data": "on"}
    same = dict(reversed(list(payload.items())))
    assert payload_fingerprint_for_payload(payload) == payload_fingerprint_for_payload(same)
    changed = {**payload, "email": "other@example.test"}
    assert payload_fingerprint_for_payload(payload) != payload_fingerprint_for_payload(changed)


def test_awaiting_user_cannot_bypass_resume_back_to_ready_for_review():
    task = TaskRecord()
    task.transition(TaskStatus.READY_FOR_REVIEW, "review prepared")
    task.transition(TaskStatus.AWAITING_USER, "waiting for explicit approval")
    with pytest.raises(ValueError, match="Invalid task transition"):
        task.transition(TaskStatus.READY_FOR_REVIEW, "bypass the human-resolution gate")


def test_resume_requires_a_paused_task_and_a_redacted_note():
    task = TaskRecord()
    with pytest.raises(ValueError, match="Only paused tasks"):
        task.resume("note")

    task.transition(TaskStatus.AWAITING_USER, "paused for human verification")
    with pytest.raises(ValueError, match="redacted human-resolution note"):
        task.resume("   ")

    task.resume("Operator completed the simulated verification step")
    assert task.status is TaskStatus.DISCOVERED
    assert any("Resumed after human resolution" in event.detail for event in task.events)
    # A resumed task must be re-inspected and freshly reviewed; it cannot submit.
    with pytest.raises(ValueError, match="not ready for approved submission"):
        task.begin_submission()
