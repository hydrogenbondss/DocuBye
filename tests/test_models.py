import pytest

from docubye.models import TaskRecord, TaskStatus


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
