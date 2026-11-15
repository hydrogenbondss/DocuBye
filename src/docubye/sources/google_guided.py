"""Guided submission for the Google contact-removal flow.

The agent prepares; the owner executes; the agent tracks the outcome honestly.
No browser automation is involved anywhere: the owner walks the real wizard in
their own everyday browser, and this module only builds the checklist, walks
them through it in the terminal, and records what they confirm.

Boundaries:
- The submission packet (field label -> exact value) is displayed in the
  terminal only. It is never written to disk, never logged, never stored.
- Task events and store rows record statuses and redacted notes only.
- SUBMITTED_BY_OWNER is recorded only after the typed gate ("I SUBMITTED")
  and a single-use approval consumption, consistent with Milestone 1.
- REMOVED is recorded only via the verify command with an evidence artifact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from uuid import uuid4

from ..models import TaskRecord, TaskStatus
from ..store import ApprovalState, TaskStore
from .google_capture import sanitize_html

SUBMITTED_CONFIRMATION = "I SUBMITTED"

_REASON_LABELS = {
    "personal": "Content contains your personal information",
    "nudity": "Content contains nudity or sexual material",
    "exploitative": "Content is on a site with exploitative removal practices",
    "minor": "Content shows a person under 18",
}
_INFO_TYPE_LABELS = {
    "contact": "Address, phone number, and/or e-mail address",
    "bank": "Bank account number",
    "credit": "Credit card number",
    "govid": "Government-issued ID document images",
    "records": "Official records",
    "credentials": "Login credentials",
    "other": "Other personal information",
}
_ID_TYPE_LABELS = {
    "drivers": "Driver's license",
    "passport": "Passport",
    "national": "National ID",
    "other-id": "Other",
}


@dataclass(frozen=True, slots=True)
class OwnerProfile:
    """Owner-approved profile values. Displayed in the terminal only."""

    reason: str
    info_type: str
    country: str
    doxxing_intent: str
    contact_email: str
    content_urls: tuple[str, ...]
    search_results_urls: tuple[str, ...] = ()
    search_terms: tuple[str, ...] = ()
    id_type: str = ""
    id_last_four: str = ""
    id_country: str = ""


@dataclass(frozen=True, slots=True)
class PacketSection:
    title: str
    entries: tuple[tuple[str, str], ...]
    conditional: bool = False


def _require_gitignored_path(path: Path, marker: tuple[str, ...], label: str) -> None:
    parts = path.resolve().parts
    for index in range(len(parts) - len(marker) + 1):
        if parts[index : index + len(marker)] == marker:
            return
    raise ValueError(f"{label} must live under {'/'.join(marker)}/ (a gitignored path); got: {path}")


def load_profile(profile_path: str | Path) -> OwnerProfile:
    """Load the owner-approved profile from a gitignored local file."""
    path = Path(profile_path)
    _require_gitignored_path(path, ("captures",), "The profile file")
    data = json.loads(path.read_text(encoding="utf-8"))

    def text(key: str) -> str:
        return str(data.get(key, "")).strip()

    def lines(key: str) -> tuple[str, ...]:
        value = data.get(key, [])
        if isinstance(value, str):
            value = [line for line in value.splitlines()]
        return tuple(str(item).strip() for item in value if str(item).strip())

    profile = OwnerProfile(
        reason=text("reason") or "personal",
        info_type=text("info_type") or "contact",
        country=text("country"),
        doxxing_intent=text("doxxing_intent"),
        contact_email=text("contact_email"),
        content_urls=lines("content_urls"),
        search_results_urls=lines("search_results_urls"),
        search_terms=lines("search_terms"),
        id_type=text("id_type"),
        id_last_four=text("id_last_four"),
        id_country=text("id_country"),
    )
    _validate_profile(profile)
    return profile


def _validate_profile(profile: OwnerProfile) -> None:
    if profile.reason not in _REASON_LABELS:
        raise ValueError(f"Unsupported reason: {profile.reason!r}")
    if profile.info_type not in _INFO_TYPE_LABELS:
        raise ValueError(f"Unsupported info_type: {profile.info_type!r}")
    missing = []
    if not profile.country:
        missing.append("country")
    if profile.doxxing_intent not in {"yes", "no"}:
        missing.append("doxxing_intent (yes/no)")
    if not profile.contact_email:
        missing.append("contact_email")
    if not profile.content_urls:
        missing.append("content_urls")
    if profile.info_type == "govid":
        if profile.id_type not in _ID_TYPE_LABELS:
            missing.append("id_type")
        if not (profile.id_last_four.isalnum() and len(profile.id_last_four) == 4):
            missing.append("id_last_four (exactly 4 letters/digits)")
        if not profile.id_country:
            missing.append("id_country")
    if missing:
        raise ValueError("Profile is missing required fields: " + ", ".join(missing))


def build_packet(profile: OwnerProfile) -> tuple[PacketSection, ...]:
    """Ordered, section-grouped checklist matching the validated wizard structure."""
    sections = [
        PacketSection("Reason for removal", (
            ("Reason", _REASON_LABELS[profile.reason]),
            ("Country of residence", profile.country),
        )),
        PacketSection("Type of personal information", (
            ("Information type", _INFO_TYPE_LABELS[profile.info_type]),
        )),
    ]
    if profile.info_type == "govid":
        sections.append(PacketSection("Government-issued ID details", (
            ("ID type", _ID_TYPE_LABELS[profile.id_type]),
            ("Last four characters of the ID", profile.id_last_four),
            ("Issuing country", profile.id_country),
        ), conditional=True))
    sections.append(PacketSection("Details", (
        ("Shared with malicious, threatening, or harassing intent?", profile.doxxing_intent),
        ("Contact email address", profile.contact_email),
        ("Specific content URLs", "\n".join(profile.content_urls)),
        ("Screenshots", "(attach your files manually in the browser)"),
        ("Google Search results page URLs", "\n".join(profile.search_results_urls) or "(leave blank)"),
        ("Search terms", "\n".join(profile.search_terms) or "(leave blank)"),
    )))
    sections.append(PacketSection("Attestations — check these yourself", (
        ("Accuracy confirmation", "(you must confirm this personally)"),
        ("Authority confirmation", "(you must confirm this personally)"),
    )))
    return tuple(sections)


def packet_fingerprint(packet: tuple[PacketSection, ...]) -> str:
    canonical = json.dumps(
        [(section.title, section.entries, section.conditional) for section in packet],
        ensure_ascii=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _redact(text: str) -> str:
    return sanitize_html(text)[0]


def run_guided_submission(
    store: TaskStore,
    task_id: str,
    profile_path: str | Path,
    *,
    prompt_fn: Callable[[str], str] = input,
    out: Callable[[str], None] = print,
) -> TaskRecord:
    """Walk the owner through the packet, then record SUBMITTED_BY_OWNER.

    The approval is recorded before the walkthrough (resumable if interrupted)
    and consumed exactly once at the typed gate.
    """
    stored = store.load_task(task_id)
    task = stored.task
    if stored.approval_state is ApprovalState.CONSUMED:
        raise PermissionError(
            "This task's approval was already consumed. If the owner submitted, record the "
            "outcome with `docubye verify`; otherwise the task needs a fresh review."
        )
    if task.status is not TaskStatus.READY_FOR_REVIEW:
        raise ValueError(
            f"Guided submission requires a ready_for_review task; this task is {task.status.value}. "
            "Run the inspection first or resume from awaiting_user."
        )

    profile = load_profile(profile_path)
    packet = build_packet(profile)
    fingerprint = packet_fingerprint(packet)

    if stored.approval_state is ApprovalState.NONE:
        submission_key = str(uuid4())
        store.record_approval(task_id, submission_key, fingerprint)
    elif stored.payload_fingerprint != fingerprint:
        raise PermissionError(
            "An approval exists for a different packet. The profile changed after approval; "
            "the task needs a fresh review."
        )

    out("\nGuided submission — you drive the browser; this tool only guides.")
    out("Open the removal form in YOUR browser and walk each section as shown.")
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
    task.transition(TaskStatus.AWAITING_CONFIRMATION, "Awaiting Google's decision; not verified")
    store.save_task(task)
    out("\nRecorded: submitted_by_owner (the human clicked the button, not the agent).")
    out("Next: when Google responds, run `docubye verify <task-id> --evidence <path> --confirm`.")
    return task


def verify_removal(
    store: TaskStore,
    task_id: str,
    evidence_path: str | Path,
    *,
    confirm: bool,
    google_confirmation: str = "",
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
    _require_gitignored_path(path, ("captures", "evidence"), "The evidence file")
    if not path.is_file():
        raise ValueError(f"Evidence file not found: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    note = "Google decision evidence recorded by owner"
    if google_confirmation.strip():
        note += f"; owner-provided confirmation (redacted): {_redact(google_confirmation.strip())[:160]}"
    store.record_evidence(task_id, "verification", path.name, digest, note)

    if not store.evidence_for(task_id):
        raise RuntimeError("Evidence artifact was not recorded; refusing to mark removed")

    task.transition(TaskStatus.REMOVED, "Removal verified by owner-provided evidence artifact")
    store.save_task(task)
    return task
