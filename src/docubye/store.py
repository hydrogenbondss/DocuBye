"""SQLite persistence for task state, approvals, and submission recovery.

The store keeps task ID, status history, approval state, submission
(idempotency) key, and confirmation ID so an interrupted run can be inspected
and recovered by a new process without ever resubmitting blindly. Form values
and page contents are never written here.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from .models import TaskEvent, TaskRecord, TaskStatus


class ApprovalState(StrEnum):
    NONE = "none"
    APPROVED = "approved"
    CONSUMED = "consumed"
    REJECTED = "rejected"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    submission_attempted INTEGER NOT NULL DEFAULT 0,
    approval_state TEXT NOT NULL DEFAULT 'none',
    submission_key TEXT,
    payload_fingerprint TEXT,
    confirmation_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS task_events (
    task_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    at TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL,
    PRIMARY KEY (task_id, seq)
);
"""


@dataclass(slots=True)
class StoredTask:
    """A task record plus its persisted submission metadata."""

    task: TaskRecord
    approval_state: ApprovalState
    submission_key: str | None
    payload_fingerprint: str | None
    confirmation_id: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStore:
    """Durable task store. One instance per process; reopen the file to restart."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._db = sqlite3.connect(self.path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        with self._db:
            self._db.executescript(_SCHEMA)
            columns = {row["name"] for row in self._db.execute("PRAGMA table_info(tasks)")}
            if "payload_fingerprint" not in columns:
                self._db.execute("ALTER TABLE tasks ADD COLUMN payload_fingerprint TEXT")

    def close(self) -> None:
        self._db.close()

    def save_task(self, task: TaskRecord) -> None:
        """Upsert the task row and append any new history events."""
        now = _now()
        with self._db:
            self._db.execute(
                """
                INSERT INTO tasks (task_id, status, submission_attempted, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status = excluded.status,
                    submission_attempted = excluded.submission_attempted,
                    updated_at = excluded.updated_at
                """,
                (task.task_id, task.status.value, int(task.submission_attempted), now, now),
            )
            row = self._db.execute(
                "SELECT COALESCE(MAX(seq), -1) AS max_seq FROM task_events WHERE task_id = ?",
                (task.task_id,),
            ).fetchone()
            next_seq = int(row["max_seq"]) + 1
            for index, event in enumerate(task.events):
                if index < next_seq:
                    continue
                self._db.execute(
                    "INSERT INTO task_events (task_id, seq, at, status, detail) VALUES (?, ?, ?, ?, ?)",
                    (task.task_id, index, event.at, event.status, event.detail),
                )

    def load_task(self, task_id: str) -> StoredTask:
        """Rebuild a task with its full history, as a new process would see it."""
        row = self._db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown task ID: {task_id}")
        event_rows = self._db.execute(
            "SELECT at, status, detail FROM task_events WHERE task_id = ? ORDER BY seq",
            (task_id,),
        ).fetchall()
        events = [TaskEvent(at=r["at"], status=r["status"], detail=r["detail"]) for r in event_rows]
        task = TaskRecord(
            task_id=row["task_id"],
            status=TaskStatus(row["status"]),
            submission_attempted=bool(row["submission_attempted"]),
            events=events,
        )
        return StoredTask(
            task=task,
            approval_state=ApprovalState(row["approval_state"]),
            submission_key=row["submission_key"],
            payload_fingerprint=row["payload_fingerprint"],
            confirmation_id=row["confirmation_id"],
        )

    def record_approval(self, task_id: str, submission_key: str, payload_fingerprint: str) -> None:
        """Persist an approval bound to this task's random submission key before submitting."""
        with self._db:
            cursor = self._db.execute(
                """
                UPDATE tasks SET approval_state = ?, submission_key = ?, payload_fingerprint = ?, updated_at = ?
                WHERE task_id = ? AND approval_state IN (?, ?)
                """,
                (ApprovalState.APPROVED.value, submission_key, payload_fingerprint, _now(), task_id,
                 ApprovalState.NONE.value, ApprovalState.REJECTED.value),
            )
        if cursor.rowcount != 1:
            raise PermissionError(f"Task {task_id} already has a consumed approval; refusing a new one")

    def record_rejection(self, task_id: str) -> None:
        with self._db:
            self._db.execute(
                "UPDATE tasks SET approval_state = ?, updated_at = ? WHERE task_id = ?",
                (ApprovalState.REJECTED.value, _now(), task_id),
            )

    def consume_approval(self, task_id: str, submission_key: str) -> None:
        """Atomically consume the approval. A consumed approval is never reusable,
        including after the process restarts and reopens the same store file.

        The approval is burned by the consume attempt itself, before the key is
        checked: a mismatched attempt must not leave the approval reusable.
        """
        with self._db:
            cursor = self._db.execute(
                """
                UPDATE tasks SET approval_state = ?, updated_at = ?
                WHERE task_id = ? AND approval_state = ?
                """,
                (ApprovalState.CONSUMED.value, _now(), task_id, ApprovalState.APPROVED.value),
            )
        if cursor.rowcount != 1:
            raise PermissionError(
                "No unused approval for this task; the original submission may already "
                "have been attempted. Recover it instead of retrying."
            )
        stored_key = self.load_task(task_id).submission_key
        if stored_key != submission_key:
            raise PermissionError("The submission key does not match the persisted approval")

    def record_confirmation_id(self, task_id: str, confirmation_id: str) -> None:
        with self._db:
            self._db.execute(
                "UPDATE tasks SET confirmation_id = ?, updated_at = ? WHERE task_id = ?",
                (confirmation_id, _now(), task_id),
            )
