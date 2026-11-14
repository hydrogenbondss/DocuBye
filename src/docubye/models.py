"""Typed task models and a deliberately restrictive workflow state machine."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from importlib import resources
from typing import Callable, Mapping
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
    # UNKNOWN may only return to AWAITING_CONFIRMATION, and only through the
    # recovery path after the original submission is found by idempotency key.
    # Automatic blind retry stays disabled.
    TaskStatus.UNKNOWN: {TaskStatus.AWAITING_CONFIRMATION},
}


def _fixture_defaults() -> dict[str, str]:
    fixture = resources.files("docubye.fixtures").joinpath("synthetic_profile.json")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    return {key: str(data[key]) for key in ("full_name", "email", "phone")}


@dataclass(frozen=True, slots=True)
class SyntheticProfile:
    """Fixed synthetic profile loaded from the packaged fixture file.

    Custom or real profiles are refused by the workflow; only the fixture
    values are accepted in this milestone.
    """

    full_name: str = field(default_factory=lambda: _fixture_defaults()["full_name"])
    email: str = field(default_factory=lambda: _fixture_defaults()["email"])
    phone: str = field(default_factory=lambda: _fixture_defaults()["phone"])

    def values(self) -> dict[str, str]:
        return {"full_name": self.full_name, "email": self.email, "phone": self.phone}


def submission_key_for_payload(payload: Mapping[str, str]) -> str:
    """Idempotency key binding one submission attempt to its exact reviewed payload."""
    canonical = json.dumps(sorted(payload.items()), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    _listeners: list[Callable[["TaskRecord"], None]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.events:
            self.events.append(self._event("Task created"))

    def _event(self, detail: str) -> TaskEvent:
        return TaskEvent(datetime.now(timezone.utc).isoformat(), self.status.value, detail)

    def add_listener(self, listener: Callable[["TaskRecord"], None]) -> None:
        """Register a persistence hook called after every recorded change."""
        self._listeners.append(listener)

    def _notify(self) -> None:
        for listener in self._listeners:
            listener(self)

    def transition(self, new_status: TaskStatus, detail: str) -> None:
        if new_status not in _ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(f"Invalid task transition: {self.status.value} -> {new_status.value}")
        self.status = new_status
        self.events.append(self._event(detail))
        self._notify()

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
