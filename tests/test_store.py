import pytest

from docubye.models import TaskRecord, TaskStatus
from docubye.store import ApprovalState, TaskStore


def _ready_task():
    task = TaskRecord()
    task.transition(TaskStatus.READY_FOR_REVIEW, "review prepared")
    return task


def test_task_roundtrip_preserves_status_and_full_history(tmp_path):
    path = tmp_path / "tasks.sqlite3"
    store = TaskStore(path)
    task = _ready_task()
    task.add_listener(store.save_task)
    store.save_task(task)
    task.transition(TaskStatus.AWAITING_USER, "paused for human verification")
    store.close()

    stored = TaskStore(path).load_task(task.task_id)
    assert stored.task.status is TaskStatus.AWAITING_USER
    assert [event.detail for event in stored.task.events] == [event.detail for event in task.events]
    assert stored.approval_state is ApprovalState.NONE
    assert stored.submission_key is None
    assert stored.confirmation_id is None


def test_approval_is_single_use_even_across_process_restarts(tmp_path):
    path = tmp_path / "tasks.sqlite3"
    store = TaskStore(path)
    task = _ready_task()
    store.save_task(task)
    store.record_approval(task.task_id, "key-1", "fingerprint-1")
    store.consume_approval(task.task_id, "key-1")
    store.close()

    # A new store instance over the same file simulates a process restart.
    reopened = TaskStore(path)
    with pytest.raises(PermissionError, match="No unused approval"):
        reopened.consume_approval(task.task_id, "key-1")
    with pytest.raises(PermissionError, match="consumed or rejected"):
        reopened.record_approval(task.task_id, "key-2", "fingerprint-2")
    stored = reopened.load_task(task.task_id)
    assert stored.approval_state is ApprovalState.CONSUMED
    assert stored.submission_key == "key-1"
    assert stored.payload_fingerprint == "fingerprint-1"


def test_a_mismatched_consume_attempt_burns_the_approval(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = _ready_task()
    store.save_task(task)
    store.record_approval(task.task_id, "key-1", "fingerprint-1")
    with pytest.raises(PermissionError, match="does not match"):
        store.consume_approval(task.task_id, "different-key")
    assert store.load_task(task.task_id).approval_state is ApprovalState.CONSUMED
    with pytest.raises(PermissionError, match="No unused approval"):
        store.consume_approval(task.task_id, "key-1")


def test_rejection_is_terminal_and_requires_a_fresh_task(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = _ready_task()
    store.save_task(task)
    store.record_rejection(task.task_id)
    with pytest.raises(PermissionError, match="consumed or rejected"):
        store.record_approval(task.task_id, "key-1", "fingerprint-1")
    assert store.load_task(task.task_id).approval_state is ApprovalState.REJECTED


def test_confirmation_id_persists_across_reopen(tmp_path):
    path = tmp_path / "tasks.sqlite3"
    store = TaskStore(path)
    task = _ready_task()
    store.save_task(task)
    store.record_confirmation_id(task.task_id, "mock-confirmation-0001")
    store.close()
    assert TaskStore(path).load_task(task.task_id).confirmation_id == "mock-confirmation-0001"


def test_load_unknown_task_id_raises(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    with pytest.raises(KeyError):
        store.load_task("no-such-task")


def test_loaded_task_still_enforces_the_state_machine(tmp_path):
    path = tmp_path / "tasks.sqlite3"
    store = TaskStore(path)
    task = _ready_task()
    store.save_task(task)
    store.close()

    stored = TaskStore(path).load_task(task.task_id)
    with pytest.raises(ValueError, match="Invalid task transition"):
        stored.task.transition(TaskStatus.VERIFIED_REMOVED, "must not skip states")
