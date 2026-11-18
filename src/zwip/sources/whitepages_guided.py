"""Guided Whitepages suppression flow (phone verification). The owner executes.

No browser automation against whitepages.com and zero network calls: the owner
works in their own browser and answers the automated verification call on their
own phone. Zwip never solves CAPTCHAs and never enters the 4-digit code —
it structures the work as a checklist and records only statuses and redacted
notes.

Whitepages is publicly self-verifiable: "verified_removed" means exactly that the
listing URL no longer shows the profile on re-search after ~72 hours.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from ..guided import PacketSection, require_gitignored_path, run_guided_flow
from ..models import TaskRecord
from ..store import TaskStore

_ALLOWED_LISTING_HOSTS = {"whitepages.com", "www.whitepages.com"}
SUPPRESSION_URL = "https://www.whitepages.com/suppression-requests"
FALLBACK_EMAIL = "privacyrequest@whitepages.com"
FALLBACK_WEBFORM = "https://www.whitepages.com/privacy"


@dataclass(frozen=True, slots=True)
class WhitepagesProfile:
    """Owner-approved Whitepages profile values. Terminal display only.

    phone_number is sensitive: the standard flow cannot complete without a
    number that can receive a live call, and it appears in the terminal packet
    and nowhere else — never in events, store rows, logs, or recorded output.
    """

    contact_email: str
    phone_number: str
    listing_urls: tuple[str, ...]
    first_name: str = ""
    last_name: str = ""
    city: str = ""
    state: str = ""


def _validate_listing_url(url: str) -> None:
    parsed = urlsplit(url.strip())
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme != "https" or host not in _ALLOWED_LISTING_HOSTS:
        raise ValueError(
            f"Listing URLs must be https URLs on whitepages.com or www.whitepages.com; got: {url!r}"
        )


def load_profile(profile_path: str | Path) -> WhitepagesProfile:
    """Load the owner-approved Whitepages profile from a gitignored local file."""
    path = Path(profile_path)
    require_gitignored_path(path, ("captures",), "The profile file")
    data = json.loads(path.read_text(encoding="utf-8"))

    def text(key: str) -> str:
        return str(data.get(key, "")).strip()

    listing_urls = data.get("listing_urls", [])
    if isinstance(listing_urls, str):
        listing_urls = [line for line in listing_urls.splitlines()]
    urls = tuple(str(item).strip() for item in listing_urls if str(item).strip())

    profile = WhitepagesProfile(
        contact_email=text("contact_email"),
        phone_number=text("phone_number"),
        listing_urls=urls,
        first_name=text("first_name"),
        last_name=text("last_name"),
        city=text("city"),
        state=text("state"),
    )
    missing = []
    if not profile.contact_email:
        missing.append("contact_email")
    if not profile.phone_number:
        missing.append(
            "phone_number (the standard flow requires a number that can receive a live call)"
        )
    if missing:
        raise ValueError("Profile is missing required fields: " + ", ".join(missing))
    if not profile.listing_urls:
        raise ValueError(
            "No listing URLs provided. Run discovery first: search whitepages.com for your "
            "name variants and copy each matching listing URL into your profile file."
        )
    for url in profile.listing_urls:
        _validate_listing_url(url)
    return profile


def build_packet(profile: WhitepagesProfile) -> tuple[PacketSection, ...]:
    """Ordered checklist for the owner-executed Whitepages suppression."""
    search_hint = " ".join(
        part for part in (profile.first_name, profile.last_name, profile.city, profile.state) if part
    ) or "(your name and location variants)"
    return (
        PacketSection("Find your listings", (
            ("Search whitepages.com for", search_hint),
            ("For each matching profile", "open it and copy its exact URL"),
            ("Listings recorded in your profile", f"{len(profile.listing_urls)} URL(s)"),
        )),
        PacketSection("Before you start", (
            ("Live phone call required", (
                "the flow places an automated call with a 4-digit code — have your phone "
                "next to you and finish ONE listing at a time"
            )),
            ("Secondary number", (
                "a secondary number (e.g. Google Voice) works if you prefer not to give "
                "Whitepages your primary number"
            )),
        )),
        PacketSection("Opt out of each listing", tuple(
            (f"Listing {index}", (
                f"1. Go to {SUPPRESSION_URL}\n"
                f"    2. Paste: {url}\n"
                "    3. Choose \"Remove Me\" and pick a removal reason\n"
                f"    4. Enter your phone number: {profile.phone_number}\n"
                "    5. Answer the automated call and enter the 4-digit code it gives you"
            ))
            for index, url in enumerate(profile.listing_urls, start=1)
        )),
        PacketSection("Confirm", (
            ("Processing window", (
                "Whitepages processes removals within about 1-72 hours; "
                "re-check each listing URL after 72 hours"
            )),
        )),
        PacketSection("Keep in mind", (
            ("Re-listing is common", "re-check quarterly"),
            ("If the form rejects you", (
                '"too many suppression requests" or a rejected number -> use the manual route: '
                f"email {FALLBACK_EMAIL} with your listing URLs, or the privacy webform "
                f"({FALLBACK_WEBFORM})"
            )),
        )),
    )


def run_whitepages_submission(
    store: TaskStore,
    task_id: str,
    profile_path: str | Path,
    *,
    prompt_fn: Callable[[str], str] | None = None,
    out: Callable[[str], None] = print,
) -> TaskRecord:
    """Build the Whitepages packet from the owner profile and run the guided flow.

    There is no inspection step: the validated profile IS the preparation, so
    a DISCOVERED task advances to READY_FOR_REVIEW when the packet is built.
    """
    profile = load_profile(profile_path)
    packet = build_packet(profile)
    return run_guided_flow(
        store, task_id, packet, source_name="Whitepages suppression",
        allow_discovered=True, prompt_fn=prompt_fn, out=out,
    )
