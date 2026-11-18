import json
import re
import shutil
import sys

import pytest

from zwip import cli
from zwip.store import TaskStore


def _profile_in_captures(tmp_path, source):
    captures = tmp_path / "captures"
    captures.mkdir(exist_ok=True)
    target = captures / "profile.local.json"
    shutil.copy(source, target)
    return target


def _run_cli(monkeypatch, capsys, argv, answers):
    prompts = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _message="": next(prompts))
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    return capsys.readouterr().out


def _printed_task_id(output):
    match = re.search(r'"task_id": "([0-9a-f-]{36})"', output)
    assert match, "no task ID in CLI output"
    return match.group(1)


def test_fresh_store_spokeo_submission_creates_task_end_to_end(monkeypatch, capsys, tmp_path):
    store = str(tmp_path / "tasks.sqlite3")
    profile = _profile_in_captures(tmp_path, "tests/fixtures/spokeo/owner_profile.example.json")

    out = _run_cli(monkeypatch, capsys, [
        "zwip", "submit-spokeo", "--profile", str(profile), "--store", store,
    ], ["", "", "", "", "I SUBMITTED"])

    assert "Created new task" in out
    task_id = _printed_task_id(out)
    stored = TaskStore(store).load_task(task_id)
    assert [e.status for e in stored.task.events] == [
        "discovered", "ready_for_review", "submitted_by_owner", "awaiting_confirmation",
    ]


def test_unknown_task_id_creates_a_fresh_task_instead_of_crashing(monkeypatch, capsys, tmp_path):
    store = str(tmp_path / "tasks.sqlite3")
    profile = _profile_in_captures(tmp_path, "tests/fixtures/whitepages/owner_profile.example.json")

    out = _run_cli(monkeypatch, capsys, [
        "zwip", "submit-whitepages", "no-such-id", "--profile", str(profile), "--store", store,
    ], ["", "", "", "", "", "I SUBMITTED"])

    assert "No task 'no-such-id' found; created new task" in out
    task_id = _printed_task_id(out)
    assert task_id != "no-such-id"
    assert TaskStore(store).load_task(task_id).task.status.value == "awaiting_confirmation"


def test_existing_task_id_is_used_not_replaced(monkeypatch, capsys, tmp_path):
    store_path = str(tmp_path / "tasks.sqlite3")
    profile = _profile_in_captures(tmp_path, "tests/fixtures/peopleconnect/owner_profile.example.json")

    first = _run_cli(monkeypatch, capsys, [
        "zwip", "submit-peopleconnect", "--profile", str(profile), "--store", store_path,
    ], ["", "", "", "", "", "I SUBMITTED"])
    task_id = _printed_task_id(first)

    # A second submission on the same task ID must fail (approval consumed) —
    # proving the existing task was used rather than silently replaced.
    with pytest.raises(PermissionError, match="already consumed"):
        _run_cli(monkeypatch, capsys, [
            "zwip", "submit-peopleconnect", task_id, "--profile", str(profile), "--store", store_path,
        ], [])
