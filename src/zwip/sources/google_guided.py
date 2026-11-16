"""Guided submission for the Google contact-removal flow.

Google-specific profile, validation, and packet content on top of the shared
guided core (zwip.guided). The owner executes the real wizard in their own
browser; this module only structures the checklist and records what they
confirm. See the core module for the standing boundaries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..guided import (
    SUBMITTED_CONFIRMATION,
    PacketSection,
    packet_fingerprint,
    require_gitignored_path,
    run_guided_flow,
    verify_removal as _verify_removal,
)
from ..models import TaskRecord
from ..store import TaskStore

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


def load_profile(profile_path: str | Path) -> OwnerProfile:
    """Load the owner-approved profile from a gitignored local file."""
    path = Path(profile_path)
    require_gitignored_path(path, ("captures",), "The profile file")
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


def run_guided_submission(
    store: TaskStore,
    task_id: str,
    profile_path: str | Path,
    *,
    prompt_fn: Callable[[str], str] = input,
    out: Callable[[str], None] = print,
) -> TaskRecord:
    """Build the Google packet from the owner profile and run the guided flow."""
    profile = load_profile(profile_path)
    packet = build_packet(profile)
    return run_guided_flow(
        store, task_id, packet, source_name="Google Search contact-info removal",
        prompt_fn=prompt_fn, out=out,
    )


def verify_removal(
    store: TaskStore,
    task_id: str,
    evidence_path: str | Path,
    *,
    confirm: bool,
    google_confirmation: str = "",
) -> TaskRecord:
    """Evidence-gated verification for the Google flow (delegates to the core)."""
    return _verify_removal(
        store, task_id, evidence_path, confirm=confirm, confirmation_note=google_confirmation
    )
