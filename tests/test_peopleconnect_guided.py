import json

import pytest

from zwip.guided import SUBMITTED_CONFIRMATION, verify_removal
from zwip.models import TaskRecord, TaskStatus
from zwip.sources.peopleconnect_guided import (
    FALLBACK_EMAIL,
    FALLBACK_PHONE,
    LOGIN_URL,
    build_packet,
    load_profile,
    run_peopleconnect_submission,
)
from zwip.store import ApprovalState, TaskStore

EXAMPLE_PROFILE = "tests/fixtures/peopleconnect/owner_profile.example.json"
DOB = "1990-01-01"


def _profile_in_captures(tmp_path, **overrides):
    data = json.loads(open(EXAMPLE_PROFILE, encoding="utf-8").read())
    data.pop("_comment", None)
    data.update(overrides)
    captures = tmp_path / "captures"
    captures.mkdir(exist_ok=True)
    path = captures / "profile.local.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _prompts(answers, calls):
    iterator = iter(answers)

    def prompt(message):
        calls.append(message)
        return next(iterator, "")

    return prompt


def test_packet_structure_and_safety_content(tmp_path):
    profile = load_profile(_profile_in_captures(tmp_path))
    packet = build_packet(profile)
    assert [section.title for section in packet] == [
        "Before you start",
        "Sign in",
        "Match your record",
        "Suppress",
        "Keep in mind",
    ]
    text = json.dumps([s.entries for s in packet])
    assert "15 minutes" in text                      # sign-in link expiry warning
    assert "Desired Behavior" in text and "Suppressed" in text
    assert "never delete the Suppression Center account" in text
    assert FALLBACK_EMAIL in text and FALLBACK_PHONE in text
    assert LOGIN_URL in text
    assert "Suppression is not deletion" in text
    assert "10 business days" in text
    assert "3-6 months" in text
    assert "Intelius" in text and "ZabaSearch" in text
    assert "Alex Example" in text and DOB in text     # terminal display only


def test_validation(tmp_path):
    with pytest.raises(ValueError, match="gitignored"):
        load_profile(tmp_path / "profile.json")
    with pytest.raises(ValueError, match="first_name"):
        load_profile(_profile_in_captures(tmp_path, first_name=""))
    with pytest.raises(ValueError, match="contact_email"):
        load_profile(_profile_in_captures(tmp_path, contact_email=""))
    for bad in ("1990/01/01", "01-01-1990", "1990-1-1", "not-a-date", ""):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            load_profile(_profile_in_captures(tmp_path, date_of_birth=bad))


def test_full_state_chain_and_typed_gate(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = TaskRecord()
    store.save_task(task)
    profile = _profile_in_captures(tmp_path)
    calls: list[str] = []

    result = run_peopleconnect_submission(
        store, task.task_id, profile,
        prompt_fn=_prompts(["", "", "", "", "", SUBMITTED_CONFIRMATION], calls),
        out=lambda _l: None,
    )
    statuses = [event.status for event in result.events]
    assert statuses == ["discovered", "ready_for_review", "submitted_by_owner", "awaiting_confirmation"]
    assert store.load_task(task.task_id).approval_state is ApprovalState.CONSUMED


def test_gate_abandon_resume_and_dob_never_recorded(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = TaskRecord()
    store.save_task(task)
    profile = _profile_in_captures(tmp_path)
    calls: list[str] = []
    out_lines: list[str] = []

    def abandon(message):
        calls.append(message)
        if "type exactly" in message:
            raise KeyboardInterrupt
        return ""

    with pytest.raises(KeyboardInterrupt):
        run_peopleconnect_submission(store, task.task_id, profile, prompt_fn=abandon, out=out_lines.append)
    stored = store.load_task(task.task_id)
    assert stored.task.status is TaskStatus.READY_FOR_REVIEW
    assert stored.approval_state is ApprovalState.APPROVED

    # The DOB is displayed in the terminal packet and nowhere else.
    assert any(DOB in line for line in out_lines)
    blob = json.dumps(stored.task.to_public_dict())
    assert DOB not in blob

    result = run_peopleconnect_submission(
        TaskStore(tmp_path / "tasks.sqlite3"), task.task_id, profile,
        prompt_fn=_prompts(["", "", "", "", "", SUBMITTED_CONFIRMATION], calls),
        out=lambda _l: None,
    )
    assert result.status is TaskStatus.AWAITING_CONFIRMATION

    blob = json.dumps(result.to_public_dict()) + json.dumps(store.evidence_for(task.task_id))
    assert DOB not in blob
    assert "alex.example@example.test" not in blob
    assert "Alex" not in blob


def test_fingerprint_mismatch_and_consume_once_across_restart(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = TaskRecord()
    store.save_task(task)
    profile = _profile_in_captures(tmp_path)
    calls: list[str] = []

    def abandon(message):
        if "type exactly" in message:
            raise KeyboardInterrupt
        return ""

    with pytest.raises(KeyboardInterrupt):
        run_peopleconnect_submission(store, task.task_id, profile, prompt_fn=abandon, out=lambda _l: None)

    changed = _profile_in_captures(tmp_path, city_ignored="", date_of_birth="1990-01-01", last_name="Else")
    with pytest.raises(PermissionError, match="different packet"):
        run_peopleconnect_submission(store, task.task_id, changed, prompt_fn=lambda _m: "", out=lambda _l: None)

    original = _profile_in_captures(tmp_path)
    result = run_peopleconnect_submission(
        TaskStore(tmp_path / "tasks.sqlite3"), task.task_id, original,
        prompt_fn=_prompts(["", "", "", "", "", SUBMITTED_CONFIRMATION], calls),
        out=lambda _l: None,
    )
    assert result.status is TaskStatus.AWAITING_CONFIRMATION
    with pytest.raises(PermissionError, match="already consumed"):
        run_peopleconnect_submission(
            TaskStore(tmp_path / "tasks.sqlite3"), task.task_id, original,
            prompt_fn=lambda _m: "", out=lambda _l: None,
        )


def test_verify_gates_and_dob_absence_in_evidence(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = TaskRecord()
    store.save_task(task)
    profile = _profile_in_captures(tmp_path)
    calls: list[str] = []
    run_peopleconnect_submission(
        store, task.task_id, profile,
        prompt_fn=_prompts(["", "", "", "", "", SUBMITTED_CONFIRMATION], calls),
        out=lambda _l: None,
    )
    evidence_dir = tmp_path / "captures" / "evidence"
    evidence_dir.mkdir(parents=True)
    evidence = evidence_dir / "portal-suppressed.png"
    evidence.write_bytes(b"synthetic screenshot bytes")

    with pytest.raises(PermissionError, match="--confirm"):
        verify_removal(store, task.task_id, evidence, confirm=False)
    with pytest.raises(ValueError, match="captures/evidence"):
        verify_removal(store, task.task_id, tmp_path / "outside.png", confirm=True)

    result = verify_removal(
        store, task.task_id, evidence, confirm=True,
        confirmation_note=f"Portal shows Suppressed for Alex Example, DOB {DOB}, alex.example@example.test",
    )
    assert result.status is TaskStatus.REMOVED
    blob = json.dumps(result.to_public_dict()) + json.dumps(store.evidence_for(task.task_id))
    assert DOB not in blob
    assert "alex.example@example.test" not in blob
    assert "Suppressed" in blob
