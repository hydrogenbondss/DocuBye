import json

import pytest

from zwip.models import TaskRecord, TaskStatus
from zwip.sources.google_guided import (
    SUBMITTED_CONFIRMATION,
    build_packet,
    load_profile,
    packet_fingerprint,
    run_guided_submission,
    verify_removal,
)
from zwip.store import ApprovalState, TaskStore

EXAMPLE_PROFILE = "tests/fixtures/google/owner_profile.example.json"


def _ready_task(store):
    task = TaskRecord()
    task.transition(TaskStatus.READY_FOR_REVIEW, "Dry-run plan prepared")
    store.save_task(task)
    return task


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


def test_packet_matches_validated_wizard_structure(tmp_path):
    profile = load_profile(_profile_in_captures(tmp_path))
    packet = build_packet(profile)
    assert [section.title for section in packet] == [
        "Reason for removal",
        "Type of personal information",
        "Details",
        "Attestations — check these yourself",
    ]
    details = dict(packet[2].entries)
    assert details["Contact email address"] == "alex.example@example.test"
    assert "example.test/listing" in details["Specific content URLs"]
    assert "Google Search results page URLs" in details
    assert "Search terms" in details
    assert "Screenshots" in details
    # Attestations are never prefilled by the tool.
    attest = dict(packet[3].entries)
    assert all("personally" in value for value in attest.values())


def test_govid_conditional_section_only_when_selected(tmp_path):
    contact = build_packet(load_profile(_profile_in_captures(tmp_path)))
    assert all("Government-issued ID" not in s.title for s in contact)

    govid = build_packet(load_profile(_profile_in_captures(
        tmp_path, info_type="govid", id_type="passport", id_last_four="9X4Z", id_country="United States",
    )))
    conditional = [s for s in govid if s.conditional]
    assert len(conditional) == 1
    entries = dict(conditional[0].entries)
    assert entries["ID type"] == "Passport"
    assert entries["Last four characters of the ID"] == "9X4Z"
    assert packet_fingerprint(contact) != packet_fingerprint(govid)


def test_profile_validation_and_path_enforcement(tmp_path):
    with pytest.raises(ValueError, match="gitignored"):
        load_profile(tmp_path / "profile.json")
    bad = _profile_in_captures(tmp_path, contact_email="")
    with pytest.raises(ValueError, match="contact_email"):
        load_profile(bad)
    bad_govid = _profile_in_captures(tmp_path, info_type="govid")
    with pytest.raises(ValueError, match="id_type"):
        load_profile(bad_govid)
    bad_last4 = _profile_in_captures(tmp_path, info_type="govid", id_type="passport", id_last_four="12345", id_country="US")
    with pytest.raises(ValueError, match="id_last_four"):
        load_profile(bad_last4)


def test_guided_gate_consumes_approval_once_and_blocks_reuse(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = _ready_task(store)
    profile = _profile_in_captures(tmp_path)
    calls: list[str] = []
    out_lines: list[str] = []

    result = run_guided_submission(
        store, task.task_id, profile,
        prompt_fn=_prompts(["", "", "", "", SUBMITTED_CONFIRMATION], calls),
        out=out_lines.append,
    )
    assert result.status is TaskStatus.AWAITING_CONFIRMATION
    statuses = [event.status for event in result.events]
    assert "submitted_by_owner" in statuses
    assert "submitting" not in statuses
    stored = store.load_task(task.task_id)
    assert stored.approval_state is ApprovalState.CONSUMED

    # The packet is displayed but never recorded: no values in events or store.
    assert any("alex.example@example.test" in line for line in out_lines)
    blob = json.dumps(result.to_public_dict()) + json.dumps(store.evidence_for(task.task_id))
    assert "alex.example@example.test" not in blob
    assert "example.test/listing" not in blob

    # A second submission attempt refuses, even after a store reopen (restart).
    with pytest.raises(PermissionError, match="already consumed"):
        run_guided_submission(
            TaskStore(tmp_path / "tasks.sqlite3"), task.task_id, profile,
            prompt_fn=_prompts([], []), out=lambda _line: None,
        )


def test_typed_gate_reprompts_and_never_records_without_it(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = _ready_task(store)
    profile = _profile_in_captures(tmp_path)
    calls: list[str] = []

    # The walkthrough is abandoned at the gate: no submitted state is recorded.
    def abandon(message):
        calls.append(message)
        if "type exactly" in message:
            raise KeyboardInterrupt
        return ""

    with pytest.raises(KeyboardInterrupt):
        run_guided_submission(store, task.task_id, profile, prompt_fn=abandon, out=lambda _l: None)
    stored = store.load_task(task.task_id)
    assert stored.task.status is TaskStatus.READY_FOR_REVIEW
    assert stored.approval_state is ApprovalState.APPROVED  # recorded, NOT consumed

    # Resume: same profile, same approval; wrong gate input re-prompts, then proceeds.
    result = run_guided_submission(
        store, task.task_id, profile,
        prompt_fn=_prompts(["", "", "", "", "submitted", SUBMITTED_CONFIRMATION], calls),
        out=lambda _l: None,
    )
    assert result.status is TaskStatus.AWAITING_CONFIRMATION
    assert any("Not confirmed" in message for message in calls)
    assert store.load_task(task.task_id).approval_state is ApprovalState.CONSUMED


def test_changed_profile_after_approval_requires_fresh_review(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = _ready_task(store)
    profile = _profile_in_captures(tmp_path)

    def abandon(message):
        if "type exactly" in message:
            raise KeyboardInterrupt
        return ""

    with pytest.raises(KeyboardInterrupt):
        run_guided_submission(store, task.task_id, profile, prompt_fn=abandon, out=lambda _l: None)

    changed = _profile_in_captures(tmp_path, search_terms=["different"])
    with pytest.raises(PermissionError, match="different packet"):
        run_guided_submission(store, task.task_id, changed, prompt_fn=lambda _m: "", out=lambda _l: None)


def test_submission_requires_ready_for_review(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = TaskRecord()
    store.save_task(task)
    with pytest.raises(ValueError, match="ready_for_review"):
        run_guided_submission(
            store, task.task_id, _profile_in_captures(tmp_path),
            prompt_fn=lambda _m: "", out=lambda _l: None,
        )


def test_removed_requires_evidence_artifact_and_confirm(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = _ready_task(store)
    profile = _profile_in_captures(tmp_path)
    calls: list[str] = []
    run_guided_submission(
        store, task.task_id, profile,
        prompt_fn=_prompts(["", "", "", "", SUBMITTED_CONFIRMATION], calls),
        out=lambda _l: None,
    )

    evidence_dir = tmp_path / "captures" / "evidence"
    evidence_dir.mkdir(parents=True)
    evidence = evidence_dir / "google-response.txt"
    evidence.write_text("Request received. Reference: G-12345 (synthetic).", encoding="utf-8")

    with pytest.raises(PermissionError, match="--confirm"):
        verify_removal(store, task.task_id, evidence, confirm=False)
    with pytest.raises(ValueError, match="captures/evidence"):
        verify_removal(store, task.task_id, tmp_path / "elsewhere.txt", confirm=True)
    with pytest.raises(ValueError, match="not found"):
        verify_removal(store, task.task_id, evidence_dir / "missing.txt", confirm=True)
    assert store.load_task(task.task_id).task.status is TaskStatus.AWAITING_CONFIRMATION

    result = verify_removal(
        store, task.task_id, evidence, confirm=True,
        google_confirmation="Ref G-12345 for alex.example@example.test",
    )
    assert result.status is TaskStatus.REMOVED
    artifacts = store.evidence_for(task.task_id)
    assert len(artifacts) == 1
    assert artifacts[0]["reference"] == "google-response.txt"
    assert len(artifacts[0]["sha256"]) == 64
    # Owner confirmation is recorded redacted; no personal values anywhere.
    blob = json.dumps(result.to_public_dict()) + json.dumps(artifacts)
    assert "alex.example@example.test" not in blob
    assert "G-12345" in blob


def test_verify_refuses_tasks_not_awaiting_confirmation(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = _ready_task(store)
    evidence_dir = tmp_path / "captures" / "evidence"
    evidence_dir.mkdir(parents=True)
    evidence = evidence_dir / "x.txt"
    evidence.write_text("synthetic", encoding="utf-8")
    with pytest.raises(ValueError, match="awaiting_confirmation"):
        verify_removal(store, task.task_id, evidence, confirm=True)


def test_state_machine_guards_guided_states():
    task = TaskRecord()
    with pytest.raises(ValueError, match="Invalid task transition"):
        task.transition(TaskStatus.SUBMITTED_BY_OWNER, "must go through review and the gate")
    task.transition(TaskStatus.READY_FOR_REVIEW, "review prepared")
    task.transition(TaskStatus.SUBMITTED_BY_OWNER, "typed gate")
    with pytest.raises(ValueError, match="Invalid task transition"):
        task.transition(TaskStatus.SUBMITTING, "owner-submitted tasks never enter the agent path")
    task.transition(TaskStatus.AWAITING_CONFIRMATION, "awaiting decision")
    task.transition(TaskStatus.REMOVED, "evidence recorded")
    with pytest.raises(ValueError, match="Invalid task transition"):
        task.transition(TaskStatus.DISCOVERED, "removed is terminal")
