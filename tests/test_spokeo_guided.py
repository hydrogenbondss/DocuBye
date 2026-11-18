import json

import pytest

from zwip.models import TaskRecord, TaskStatus
from zwip.sources.spokeo_guided import (
    OPT_OUT_URL,
    build_packet,
    load_profile,
    run_spokeo_submission,
)
from zwip.guided import SUBMITTED_CONFIRMATION, verify_removal
from zwip.store import ApprovalState, TaskStore

EXAMPLE_PROFILE = "tests/fixtures/spokeo/owner_profile.example.json"


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


def test_packet_structure_and_per_url_iteration(tmp_path):
    profile = load_profile(_profile_in_captures(tmp_path))
    packet = build_packet(profile)
    assert [section.title for section in packet] == [
        "Find your listings",
        "Opt out of each listing",
        "Confirm by email",
        "Keep in mind",
    ]
    opt_out = dict(packet[1].entries)
    assert list(opt_out) == ["Listing 1", "Listing 2"]
    assert OPT_OUT_URL in opt_out["Listing 1"]
    assert "https://www.spokeo.com/Example-Person/California-Synthetic" in opt_out["Listing 1"]
    assert "https://www.spokeo.com/Example-Person/New-York-Synthetic" in opt_out["Listing 2"]
    assert "CAPTCHA yourself" in opt_out["Listing 1"]
    # The packet shows the exact value to enter (same contract as Whitepages).
    assert "alex.example@example.test" in opt_out["Listing 1"]
    confirm = dict(packet[2].entries)
    assert "NOT processed" in confirm["Verification link"]
    assert "quarterly" in dict(packet[3].entries)["Reappearance"]


def test_listing_url_validation(tmp_path):
    with pytest.raises(ValueError, match="spokeo.com"):
        load_profile(_profile_in_captures(tmp_path, listing_urls=["https://www.whitepages.com/x"]))
    with pytest.raises(ValueError, match="https"):
        load_profile(_profile_in_captures(tmp_path, listing_urls=["http://www.spokeo.com/x"]))
    with pytest.raises(ValueError, match="spokeo.com"):
        load_profile(_profile_in_captures(tmp_path, listing_urls=["https://www.spokeo.com.evil.test/x"]))
    with pytest.raises(ValueError, match="discovery"):
        load_profile(_profile_in_captures(tmp_path, listing_urls=[]))
    with pytest.raises(ValueError, match="gitignored"):
        load_profile(tmp_path / "profile.json")


def test_discovered_task_reaches_owner_submitted_via_gate(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = TaskRecord()
    store.save_task(task)
    profile = _profile_in_captures(tmp_path)
    calls: list[str] = []
    out_lines: list[str] = []

    result = run_spokeo_submission(
        store, task.task_id, profile,
        prompt_fn=_prompts(["", "", "", "", SUBMITTED_CONFIRMATION], calls),
        out=out_lines.append,
    )
    statuses = [event.status for event in result.events]
    assert statuses == ["discovered", "ready_for_review", "submitted_by_owner", "awaiting_confirmation"]
    stored = store.load_task(task.task_id)
    assert stored.approval_state is ApprovalState.CONSUMED

    # No profile values anywhere outside the terminal display.
    assert any("Example-Person/California-Synthetic" in line for line in out_lines)
    assert any("alex.example@example.test" in line for line in out_lines)
    blob = json.dumps(result.to_public_dict()) + json.dumps(store.evidence_for(task.task_id))
    assert "alex.example@example.test" not in blob
    assert "Example-Person" not in blob


def test_consume_once_across_restart_and_fingerprint_mismatch(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = TaskRecord()
    store.save_task(task)
    profile = _profile_in_captures(tmp_path)
    calls: list[str] = []

    def abandon(message):
        calls.append(message)
        if "type exactly" in message:
            raise KeyboardInterrupt
        return ""

    with pytest.raises(KeyboardInterrupt):
        run_spokeo_submission(store, task.task_id, profile, prompt_fn=abandon, out=lambda _l: None)
    stored = store.load_task(task.task_id)
    assert stored.task.status is TaskStatus.READY_FOR_REVIEW
    assert stored.approval_state is ApprovalState.APPROVED

    # Changed profile after approval -> fingerprint mismatch -> fresh review required.
    changed = _profile_in_captures(tmp_path, city="Otherville")
    with pytest.raises(PermissionError, match="different packet"):
        run_spokeo_submission(store, task.task_id, changed, prompt_fn=lambda _m: "", out=lambda _l: None)

    # Resume with the unchanged profile from a reopened store (simulated restart).
    original = _profile_in_captures(tmp_path)
    result = run_spokeo_submission(
        TaskStore(tmp_path / "tasks.sqlite3"), task.task_id, original,
        prompt_fn=_prompts(["", "", "", "", SUBMITTED_CONFIRMATION], calls),
        out=lambda _l: None,
    )
    assert result.status is TaskStatus.AWAITING_CONFIRMATION

    # A second submission attempt refuses after another restart.
    with pytest.raises(PermissionError, match="already consumed"):
        run_spokeo_submission(
            TaskStore(tmp_path / "tasks.sqlite3"), task.task_id, original,
            prompt_fn=lambda _m: "", out=lambda _l: None,
        )


def test_verify_gates_apply_to_spokeo_tasks(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = TaskRecord()
    store.save_task(task)
    profile = _profile_in_captures(tmp_path)
    calls: list[str] = []
    run_spokeo_submission(
        store, task.task_id, profile,
        prompt_fn=_prompts(["", "", "", "", SUBMITTED_CONFIRMATION], calls),
        out=lambda _l: None,
    )
    evidence_dir = tmp_path / "captures" / "evidence"
    evidence_dir.mkdir(parents=True)
    evidence = evidence_dir / "re-search.png"
    evidence.write_bytes(b"synthetic screenshot bytes")

    with pytest.raises(PermissionError, match="--confirm"):
        verify_removal(store, task.task_id, evidence, confirm=False)
    with pytest.raises(ValueError, match="captures/evidence"):
        verify_removal(store, task.task_id, tmp_path / "outside.png", confirm=True)

    result = verify_removal(
        store, task.task_id, evidence, confirm=True,
        confirmation_note="Confirmation email for alex.example@example.test received",
    )
    assert result.status is TaskStatus.VERIFIED_REMOVED
    blob = json.dumps(result.to_public_dict()) + json.dumps(store.evidence_for(task.task_id))
    assert "alex.example@example.test" not in blob
