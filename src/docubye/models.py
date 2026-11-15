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
    SUBMITTED_BY_OWNER = "submitted_by_owner"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    VERIFIED_REMOVED = "verified_removed"
    REMOVED = "removed"
    REJECTED = "rejected"
    FAILED = "failed"
    UNKNOWN = "unknown"


_ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.DISCOVERED: {TaskStatus.READY_FOR_REVIEW, TaskStatus.AWAITING_USER, TaskStatus.FAILED},
    # SUBMITTING is the agent-driven path; SUBMITTED_BY_OWNER is reachable only
    # through the guided gate (typed owner confirmation + consumed approval).
    TaskStatus.READY_FOR_REVIEW: {
        TaskStatus.AWAITING_USER, TaskStatus.SUBMITTING, TaskStatus.SUBMITTED_BY_OWNER,
        TaskStatus.REJECTED, TaskStatus.FAILED,
    },
    # AWAITING_USER may leave only through resume() (to DISCOVERED, forcing fresh
    # inspection and review), REJECTED, or FAILED. There is no direct path back
    # to READY_FOR_REVIEW: caller code cannot bypass the human-resolution gate.
    TaskStatus.AWAITING_USER: {TaskStatus.DISCOVERED, TaskStatus.REJECTED, TaskStatus.FAILED},
    TaskStatus.SUBMITTING: {TaskStatus.SUBMITTED, TaskStatus.UNKNOWN, TaskStatus.FAILED},
    TaskStatus.SUBMITTED: {TaskStatus.AWAITING_CONFIRMATION, TaskStatus.UNKNOWN, TaskStatus.FAILED},
    # The owner clicked the button in their own browser; the agent only recorded it.
    TaskStatus.SUBMITTED_BY_OWNER: {TaskStatus.AWAITING_CONFIRMATION, TaskStatus.FAILED},
    # REMOVED is reachable only via the verify command with a recorded evidence
    # artifact; never from submission alone.
    TaskStatus.AWAITING_CONFIRMATION: {TaskStatus.VERIFIED_REMOVED, TaskStatus.REMOVED, TaskStatus.UNKNOWN, TaskStatus.FAILED},
    TaskStatus.VERIFIED_REMOVED: set(),
    TaskStatus.REMOVED: set(),
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


def payload_fingerprint_for_payload(payload: Mapping[str, str]) -> str:
    """Digest of the exact reviewed payload, for payload-match checking only.

    This is not the idempotency key: each task gets its own random submission
    key so two tasks with identical data never collapse into one record.
    """
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

    def resume(self, resolution_note: str) -> None:
        """Resume a paused task after a human resolved the blocking step.

        Lands on DISCOVERED so the workflow re-inspects the page and prepares a
        fresh review; it never resumes into SUBMITTING. The note must be
        pre-redacted by the caller and is truncated defensively.
        """
        if self.status is not TaskStatus.AWAITING_USER:
            raise ValueError(f"Only paused tasks can resume; this task is {self.status.value}")
        note = resolution_note.strip()[:160]
        if not note:
            raise ValueError("A redacted human-resolution note is required to resume")
        self.status = TaskStatus.DISCOVERED
        self.events.append(self._event(f"Resumed after human resolution: {note}"))
        self._notify()

    def to_public_dict(self) -> dict[str, object]:
        """Return an audit record safe for ordinary logs."""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "submission_attempted": self.submission_attempted,
            "events": [asdict(event) for event in self.events],
        }
