"""Source-agnostic guided-submission core.

The agent prepares; the owner executes; the agent tracks the outcome honestly.
No browser automation is involved: the owner walks the real source flow in
their own everyday browser, and this module only structures the checklist,
walks them through it in the terminal, and records what they confirm.

Boundaries (shared by every source adapter):
- The submission packet (field label -> exact value) is displayed in the
  terminal only. It is never written to disk, never logged, never stored.
- Task events and store rows record statuses and redacted notes only.
- SUBMITTED_BY_OWNER is recorded only after the typed gate ("I SUBMITTED")
  and a single-use approval consumption, consistent with Milestone 1.
- REMOVED is recorded only via verification with an evidence artifact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .models import TaskRecord, TaskStatus
from .sources.google_capture import sanitize_html
from .store import ApprovalState, TaskStore

SUBMITTED_CONFIRMATION = "I SUBMITTED"


@dataclass(frozen=True, slots=True)
class PacketSection:
    title: str
    entries: tuple[tuple[str, str], ...]
    conditional: bool = False


def require_gitignored_path(path: Path, marker: tuple[str, ...], label: str) -> None:
    parts = path.resolve().parts
    for index in range(len(parts) - len(marker) + 1):
        if parts[index : index + len(marker)] == marker:
            return
    raise ValueError(f"{label} must live under {'/'.join(marker)}/ (a gitignored path); got: {path}")


def packet_fingerprint(packet: tuple[PacketSection, ...]) -> str:
    canonical = json.dumps(
        [(section.title, section.entries, section.conditional) for section in packet],
        ensure_ascii=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def redact_text(text: str) -> str:
    """Strip emails/phones/account markers from free text before it is recorded."""
    return sanitize_html(text)[0]


def run_guided_flow(
    store: TaskStore,
    task_id: str,
    packet: tuple[PacketSection, ...],
    *,
    source_name: str,
    allow_discovered: bool = False,
    prompt_fn: Callable[[str], str] | None = None,
    out: Callable[[str], None] = print,
) -> TaskRecord:
    """Walk the owner through the packet, then record SUBMITTED_BY_OWNER.

    The approval is recorded before the walkthrough (resumable if interrupted)
    and consumed exactly once at the typed gate. Sources whose validation IS
    the profile (e.g. Spokeo) pass allow_discovered=True so a DISCOVERED task
    moves to READY_FOR_REVIEW when its packet is prepared; sources with a
    separate inspection step (e.g. Google) require READY_FOR_REVIEW already.
    """
    stored = store.load_task(task_id)
    task = stored.task
    if stored.approval_state is ApprovalState.CONSUMED:
        raise PermissionError(
            "This task's approval was already consumed. If the owner submitted, record the "
            "outcome with `zwip verify`; otherwise the task needs a fresh review."
        )
    if task.status is TaskStatus.DISCOVERED and allow_discovered:
        task.transition(TaskStatus.READY_FOR_REVIEW, f"{source_name} packet prepared from owner profile")
        store.save_task(task)
    elif task.status is not TaskStatus.READY_FOR_REVIEW:
        raise ValueError(
            f"Guided submission requires a ready_for_review task; this task is {task.status.value}. "
            "Run the inspection first or resume from awaiting_user."
        )

    fingerprint = packet_fingerprint(packet)
    if stored.approval_state is ApprovalState.NONE:
        submission_key = str(uuid4())
        store.record_approval(task_id, submission_key, fingerprint)
    elif stored.payload_fingerprint != fingerprint:
        raise PermissionError(
            "An approval exists for a different packet. The profile changed after approval; "
            "the task needs a fresh review."
        )

    prompt_fn = prompt_fn or input
    out(f"\nGuided submission ({source_name}) — you drive the browser; this tool only guides.")
    out("Open the source in YOUR browser and walk each section as shown.")
    for index, section in enumerate(packet, start=1):
        marker = " (conditional section)" if section.conditional else ""
        out(f"\nSection {index}/{len(packet)}: {section.title}{marker}")
        for label, value in section.entries:
            out(f"  {label}:\n    {value}")
        answer = prompt_fn("Press Enter alone when this section is done: ")
        while answer.strip():
            answer = prompt_fn("No input expected — press Enter alone when done: ")

    confirmation = prompt_fn(f"Only AFTER you clicked Submit yourself, type exactly: {SUBMITTED_CONFIRMATION}\n> ")
    while confirmation.strip() != SUBMITTED_CONFIRMATION:
        confirmation = prompt_fn(f"Not confirmed. Type exactly: {SUBMITTED_CONFIRMATION}\n> ")

    store.consume_approval(task_id, store.load_task(task_id).submission_key)
    task.transition(
        TaskStatus.SUBMITTED_BY_OWNER,
        "Owner confirmed their own submission via the typed gate; approval consumed once",
    )
    store.save_task(task)
    task.transition(TaskStatus.AWAITING_CONFIRMATION, "Awaiting the source's confirmation; not verified")
    store.save_task(task)
    out("\nRecorded: submitted_by_owner (the human clicked the button, not the agent).")
    out("Next: when the source confirms, run `zwip verify <task-id> --evidence <path> --confirm`.")
    return task


def verify_removal(
    store: TaskStore,
    task_id: str,
    evidence_path: str | Path,
    *,
    confirm: bool,
    confirmation_note: str = "",
) -> TaskRecord:
    """Record a verification artifact and transition the task to REMOVED.

    The evidence file must live under captures/evidence/ (gitignored). Without
    a recorded artifact the task can never be labelled removed.
    """
    if not confirm:
        raise PermissionError("Verification requires the explicit --confirm flag")
    stored = store.load_task(task_id)
    task = stored.task
    if task.status is not TaskStatus.AWAITING_CONFIRMATION:
        raise ValueError(
            f"Verification requires an awaiting_confirmation task; this task is {task.status.value}. "
            "A task is never labelled removed from submission alone."
        )

    path = Path(evidence_path)
    require_gitignored_path(path, ("captures", "evidence"), "The evidence file")
    if not path.is_file():
        raise ValueError(f"Evidence file not found: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    note = "Source decision evidence recorded by owner"
    if confirmation_note.strip():
        note += f"; owner-provided confirmation (redacted): {redact_text(confirmation_note.strip())[:160]}"
    store.record_evidence(task_id, "verification", path.name, digest, note)

    if not store.evidence_for(task_id):
        raise RuntimeError("Evidence artifact was not recorded; refusing to mark removed")

    task.transition(TaskStatus.REMOVED, "Removal verified by owner-provided evidence artifact")
    store.save_task(task)
    return task
