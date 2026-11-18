"""Guided PeopleConnect Suppression Center flow. The owner executes; the tool guides and tracks.

PeopleConnect refuses authorized-agent submissions, so owner-executed is the
ONLY route — this adapter is guided-only by design, not by limitation. No
browser automation, zero network calls, and no CAPTCHA bypass: everything
happens in the owner's own everyday browser.

One Suppression Center suppression covers Intelius, TruthFinder, Instant
Checkmate, US Search, ZabaSearch, and other PeopleConnect brands. Suppression
is NOT deletion of the underlying records.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..guided import PacketSection, require_gitignored_path, run_guided_flow
from ..models import TaskRecord
from ..store import TaskStore

LOGIN_URL = "https://suppression.peopleconnect.us/login"
FALLBACK_EMAIL = "privacy@peopleconnect.us"
FALLBACK_PHONE = "(800) 699-8081"
_DOB_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True, slots=True)
class PeopleConnectProfile:
    """Owner-approved PeopleConnect profile values. Terminal display only.

    date_of_birth is the most sensitive field handled so far: it appears in
    the terminal packet and nowhere else — never in events, store rows, logs,
    or recorded output.
    """

    contact_email: str
    first_name: str
    last_name: str
    date_of_birth: str
    middle_name: str = ""
    previous_names: tuple[str, ...] = ()


def load_profile(profile_path: str | Path) -> PeopleConnectProfile:
    """Load the owner-approved profile from a gitignored local file."""
    path = Path(profile_path)
    require_gitignored_path(path, ("captures",), "The profile file")
    data = json.loads(path.read_text(encoding="utf-8"))

    def text(key: str) -> str:
        return str(data.get(key, "")).strip()

    previous = data.get("previous_names", [])
    if isinstance(previous, str):
        previous = [line for line in previous.splitlines()]
    profile = PeopleConnectProfile(
        contact_email=text("contact_email"),
        first_name=text("first_name"),
        last_name=text("last_name"),
        date_of_birth=text("date_of_birth"),
        middle_name=text("middle_name"),
        previous_names=tuple(str(item).strip() for item in previous if str(item).strip()),
    )
    _validate_profile(profile)
    return profile


def _validate_profile(profile: PeopleConnectProfile) -> None:
    missing = []
    if not profile.contact_email:
        missing.append("contact_email")
    if not profile.first_name:
        missing.append("first_name")
    if not profile.last_name:
        missing.append("last_name")
    if missing:
        raise ValueError("Profile is missing required fields: " + ", ".join(missing))
    if not _DOB_RE.fullmatch(profile.date_of_birth):
        raise ValueError("date_of_birth must be in YYYY-MM-DD format")


def build_packet(profile: PeopleConnectProfile) -> tuple[PacketSection, ...]:
    """Ordered checklist for the owner-executed PeopleConnect suppression."""
    name_line = " ".join(
        part for part in (profile.first_name, profile.middle_name, profile.last_name) if part
    )
    if profile.previous_names:
        name_line += " (also: " + ", ".join(profile.previous_names) + ")"
    return (
        PacketSection("Before you start", (
            ("Use an email alias", "if you have one, use it as your contact email"),
            ("Plan one sitting", (
                "the sign-in link PeopleConnect emails you expires in about 15 minutes — "
                "have immediate access to that inbox before you begin"
            )),
        )),
        PacketSection("Sign in", (
            ("Go to", LOGIN_URL),
            ("Enter", "your contact email"),
            ("Emailed sign-in link", (
                "click it within ~15 minutes (check spam; if it expires, restart — that is normal)"
            )),
        )),
        PacketSection("Match your record", (
            ("Legal name", name_line),
            ("Date of birth", profile.date_of_birth),
            ("Enter these exactly as they appear in public records", ""),
            ("Select the record that matches you", ""),
            ("If verification can only go to an old email/phone you no longer control", (
                f"stop the online flow and email {FALLBACK_EMAIL} or call {FALLBACK_PHONE} "
                "with your name, date of birth, and the addresses on the listing"
            )),
        )),
        PacketSection("Suppress", (
            ("On the matched record", 'set the visibility / "Desired Behavior" dropdown to "Suppressed" and save'),
            ("CRITICAL", (
                "never delete the Suppression Center account afterwards — deleting it erases "
                "the standing suppression instruction while the data pipeline keeps flowing"
            )),
        )),
        PacketSection("Keep in mind", (
            ("Coverage", (
                "one suppression covers Intelius, TruthFinder, Instant Checkmate, US Search, "
                "ZabaSearch, and other PeopleConnect brands"
            )),
            ("Suppression is not deletion", "the underlying records still exist"),
            ("Propagation", "allow up to 10 business days"),
            ("Re-check", (
                "every 3-6 months: newly ingested records (new address, name variant) can "
                "surface unlinked to your suppression"
            )),
        )),
    )


def run_peopleconnect_submission(
    store: TaskStore,
    task_id: str,
    profile_path: str | Path,
    *,
    prompt_fn: Callable[[str], str] | None = None,
    out: Callable[[str], None] = print,
) -> TaskRecord:
    """Build the PeopleConnect packet from the owner profile and run the guided flow.

    There is no inspection step: the validated profile IS the preparation, so
    a DISCOVERED task advances to READY_FOR_REVIEW when the packet is built.
    """
    profile = load_profile(profile_path)
    packet = build_packet(profile)
    return run_guided_flow(
        store, task_id, packet, source_name="PeopleConnect Suppression Center",
        allow_discovered=True, prompt_fn=prompt_fn, out=out,
    )
