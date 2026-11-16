import json

import pytest

from docubye.guided import SUBMITTED_CONFIRMATION, verify_removal
from docubye.models import TaskRecord, TaskStatus
from docubye.sources.whitepages_guided import (
    FALLBACK_EMAIL,
    SUPPRESSION_URL,
    build_packet,
    load_profile,
    run_whitepages_submission,
)
from docubye.store import ApprovalState, TaskStore

EXAMPLE_PROFILE = "tests/fixtures/whitepages/owner_profile.example.json"
PHONE = "+1 202 555 0147"


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


def test_packet_structure_and_per_url_phone_steps(tmp_path):
    profile = load_profile(_profile_in_captures(tmp_path))
    packet = build_packet(profile)
    assert [section.title for section in packet] == [
        "Find your listings",
        "Before you start",
        "Opt out of each listing",
        "Confirm",
        "Keep in mind",
    ]
    opt_out = dict(packet[2].entries)
    assert list(opt_out) == ["Listing 1", "Listing 2"]
    for entry in opt_out.values():
        assert SUPPRESSION_URL in entry
        assert "automated call" in entry
        assert "4-digit code" in entry
    text = json.dumps([s.entries for s in packet])
    assert "Google Voice" in text              # secondary-number guidance
    assert FALLBACK_EMAIL in text              # manual-route fallback
    assert "72 hours" in text
    assert "quarterly" in text
    assert PHONE in text                       # terminal display only


def test_validation(tmp_path):
    with pytest.raises(ValueError, match="gitignored"):
        load_profile(tmp_path / "profile.json")
    with pytest.raises(ValueError, match="whitepages.com"):
        load_profile(_profile_in_captures(tmp_path, listing_urls=["https://www.spokeo.com/x"]))
    with pytest.raises(ValueError, match="https"):
        load_profile(_profile_in_captures(tmp_path, listing_urls=["http://www.whitepages.com/x"]))
    with pytest.raises(ValueError, match="whitepages.com"):
        load_profile(_profile_in_captures(tmp_path, listing_urls=["https://www.whitepages.com.evil.test/x"]))
    with pytest.raises(ValueError, match="discovery"):
        load_profile(_profile_in_captures(tmp_path, listing_urls=[]))
    with pytest.raises(ValueError, match="live call"):
        load_profile(_profile_in_captures(tmp_path, phone_number=""))


def test_full_state_chain_and_typed_gate(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = TaskRecord()
    store.save_task(task)
    profile = _profile_in_captures(tmp_path)
    calls: list[str] = []

    result = run_whitepages_submission(
        store, task.task_id, profile,
        prompt_fn=_prompts(["", "", "", "", "", SUBMITTED_CONFIRMATION], calls),
        out=lambda _l: None,
    )
    statuses = [event.status for event in result.events]
    assert statuses == ["discovered", "ready_for_review", "submitted_by_owner", "awaiting_confirmation"]
    assert store.load_task(task.task_id).approval_state is ApprovalState.CONSUMED


def test_gate_abandon_resume_and_phone_never_recorded(tmp_path):
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
        run_whitepages_submission(store, task.task_id, profile, prompt_fn=abandon, out=out_lines.append)
    stored = store.load_task(task.task_id)
    assert stored.task.status is TaskStatus.READY_FOR_REVIEW
    assert stored.approval_state is ApprovalState.APPROVED

    # Phone displayed in the terminal packet, recorded nowhere.
    assert any(PHONE in line for line in out_lines)
    assert PHONE not in json.dumps(stored.task.to_public_dict())

    result = run_whitepages_submission(
        TaskStore(tmp_path / "tasks.sqlite3"), task.task_id, profile,
        prompt_fn=_prompts(["", "", "", "", "", SUBMITTED_CONFIRMATION], calls),
        out=lambda _l: None,
    )
    assert result.status is TaskStatus.AWAITING_CONFIRMATION
    blob = json.dumps(result.to_public_dict()) + json.dumps(store.evidence_for(task.task_id))
    assert PHONE not in blob
    assert "alex.example@example.test" not in blob
    assert "Alex-Example" not in blob


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
        run_whitepages_submission(store, task.task_id, profile, prompt_fn=abandon, out=lambda _l: None)

    changed = _profile_in_captures(tmp_path, city="Otherville")
    with pytest.raises(PermissionError, match="different packet"):
        run_whitepages_submission(store, task.task_id, changed, prompt_fn=lambda _m: "", out=lambda _l: None)

    original = _profile_in_captures(tmp_path)
    result = run_whitepages_submission(
        TaskStore(tmp_path / "tasks.sqlite3"), task.task_id, original,
        prompt_fn=_prompts(["", "", "", "", "", SUBMITTED_CONFIRMATION], calls),
        out=lambda _l: None,
    )
    assert result.status is TaskStatus.AWAITING_CONFIRMATION
    with pytest.raises(PermissionError, match="already consumed"):
        run_whitepages_submission(
            TaskStore(tmp_path / "tasks.sqlite3"), task.task_id, original,
            prompt_fn=lambda _m: "", out=lambda _l: None,
        )


def test_verify_gates_and_phone_absence_in_evidence(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = TaskRecord()
    store.save_task(task)
    profile = _profile_in_captures(tmp_path)
    calls: list[str] = []
    run_whitepages_submission(
        store, task.task_id, profile,
        prompt_fn=_prompts(["", "", "", "", "", SUBMITTED_CONFIRMATION], calls),
        out=lambda _l: None,
    )
    evidence_dir = tmp_path / "captures" / "evidence"
    evidence_dir.mkdir(parents=True)
    evidence = evidence_dir / "empty-research.png"
    evidence.write_bytes(b"synthetic screenshot bytes")

    with pytest.raises(PermissionError, match="--confirm"):
        verify_removal(store, task.task_id, evidence, confirm=False)
    with pytest.raises(ValueError, match="captures/evidence"):
        verify_removal(store, task.task_id, tmp_path / "outside.png", confirm=True)

    result = verify_removal(
        store, task.task_id, evidence, confirm=True,
        confirmation_note=f"Listing gone on re-search for {PHONE} / alex.example@example.test",
    )
    assert result.status is TaskStatus.REMOVED
    blob = json.dumps(result.to_public_dict()) + json.dumps(store.evidence_for(task.task_id))
    assert PHONE not in blob
    assert "alex.example@example.test" not in blob
