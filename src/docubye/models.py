"""Typed task models and a deliberately restrictive workflow state machine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4


class TaskStatus(StrEnum):
    DISCOVERED = "discovered"
    READY_FOR_REVIEW = "ready_for_review"
    AWAITING_USER = "awaiting_user"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    VERIFIED_REMOVED = "verified_removed"
    REJECTED = "rejected"
    FAILED = "failed"
    UNKNOWN = "unknown"


_ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.DISCOVERED: {TaskStatus.READY_FOR_REVIEW, TaskStatus.AWAITING_USER, TaskStatus.FAILED},
    TaskStatus.READY_FOR_REVIEW: {TaskStatus.AWAITING_USER, TaskStatus.SUBMITTING, TaskStatus.REJECTED, TaskStatus.FAILED},
    TaskStatus.AWAITING_USER: {TaskStatus.READY_FOR_REVIEW, TaskStatus.REJECTED, TaskStatus.FAILED},
    TaskStatus.SUBMITTING: {TaskStatus.SUBMITTED, TaskStatus.UNKNOWN, TaskStatus.FAILED},
    TaskStatus.SUBMITTED: {TaskStatus.AWAITING_CONFIRMATION, TaskStatus.UNKNOWN, TaskStatus.FAILED},
    TaskStatus.AWAITING_CONFIRMATION: {TaskStatus.VERIFIED_REMOVED, TaskStatus.UNKNOWN, TaskStatus.FAILED},
    TaskStatus.VERIFIED_REMOVED: set(),
    TaskStatus.REJECTED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.UNKNOWN: set(),
}


@dataclass(frozen=True, slots=True)
class SyntheticProfile:
    """Fixed synthetic profile for this milestone; custom/real profiles are refused."""

    full_name: str = "Alex Example"
    email: str = "alex.example@example.test"
    phone: str = "+1 202 555 0147"

    def values(self) -> dict[str, str]:
        return {"full_name": self.full_name, "email": self.email, "phone": self.phone}


@dataclass(frozen=True, slots=True)
class TaskEvent:
    at: str
    status: str
    detail: str


@dataclass(slots=True)
class TaskRecord:
    """Progress evidence deliberately stores no form values or page contents."""

    task_id: str = field(default_factory=lambda: str(uuid4()))
    status: TaskStatus = TaskStatus.DISCOVERED
    submission_attempted: bool = False
    events: list[TaskEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.events:
            self.events.append(self._event("Task created"))

    def _event(self, detail: str) -> TaskEvent:
        return TaskEvent(datetime.now(timezone.utc).isoformat(), self.status.value, detail)

    def transition(self, new_status: TaskStatus, detail: str) -> None:
        if new_status not in _ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(f"Invalid task transition: {self.status.value} -> {new_status.value}")
        self.status = new_status
        self.events.append(self._event(detail))

    def begin_submission(self) -> None:
        if self.submission_attempted:
            raise ValueError("Submission already attempted; refusing to submit twice")
        if self.status is not TaskStatus.READY_FOR_REVIEW:
            raise ValueError("Task is not ready for approved submission")
        self.submission_attempted = True
        self.transition(TaskStatus.SUBMITTING, "Approved submission started")

    def to_public_dict(self) -> dict[str, object]:
        """Return an audit record safe for ordinary logs."""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "submission_attempted": self.submission_attempted,
            "events": [asdict(event) for event in self.events],
        }
