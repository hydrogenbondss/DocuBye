"""Guided Spokeo opt-out. The owner executes; the tool guides and tracks.

No browser automation against spokeo.com and zero network calls: the owner
searches for their own listings, opts out of each one themselves (solving any
CAPTCHA personally — Zwip never solves CAPTCHAs), and confirms the emailed
verification link. This module structures that work as a checklist and records
only statuses and redacted notes.

"Removed" means exactly this: the listing URL no longer shows the profile on
re-check (public re-search after Spokeo's processing window). Nothing more.
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

_ALLOWED_LISTING_HOSTS = {"spokeo.com", "www.spokeo.com"}
OPT_OUT_URL = "https://www.spokeo.com/optout"


@dataclass(frozen=True, slots=True)
class SpokeoProfile:
    """Owner-approved Spokeo profile values. Displayed in the terminal only.

    Name/city/state are used only to compose discovery guidance text; the
    listing URLs are the actionable input.
    """

    contact_email: str
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
            f"Listing URLs must be https URLs on spokeo.com or www.spokeo.com; got: {url!r}"
        )


def load_profile(profile_path: str | Path) -> SpokeoProfile:
    """Load the owner-approved Spokeo profile from a gitignored local file."""
    path = Path(profile_path)
    require_gitignored_path(path, ("captures",), "The profile file")
    data = json.loads(path.read_text(encoding="utf-8"))

    def text(key: str) -> str:
        return str(data.get(key, "")).strip()

    listing_urls = data.get("listing_urls", [])
    if isinstance(listing_urls, str):
        listing_urls = [line for line in listing_urls.splitlines()]
    urls = tuple(str(item).strip() for item in listing_urls if str(item).strip())

    profile = SpokeoProfile(
        contact_email=text("contact_email"),
        listing_urls=urls,
        first_name=text("first_name"),
        last_name=text("last_name"),
        city=text("city"),
        state=text("state"),
    )
    if not profile.contact_email:
        raise ValueError("Profile is missing required fields: contact_email")
    if not profile.listing_urls:
        raise ValueError(
            "No listing URLs provided. Run discovery first: search spokeo.com for your "
            "name variants and copy each matching listing URL into your profile file."
        )
    for url in profile.listing_urls:
        _validate_listing_url(url)
    return profile


def build_packet(profile: SpokeoProfile) -> tuple[PacketSection, ...]:
    """Ordered checklist for the owner-executed Spokeo opt-out."""
    search_hint = " ".join(
        part for part in (profile.first_name, profile.last_name, profile.city, profile.state) if part
    ) or "(your name and location variants)"
    sections = [
        PacketSection("Find your listings", (
            ("Search spokeo.com for", search_hint),
            ("For each matching listing", "open it and copy its exact URL"),
            ("Listings recorded in your profile", f"{len(profile.listing_urls)} URL(s)"),
        )),
        PacketSection("Opt out of each listing", tuple(
            (f"Listing {index}", (
                f"1. Go to {OPT_OUT_URL}\n"
                f"    2. Paste: {url}\n"
                f"    3. Enter your contact email\n"
                "    4. Solve the CAPTCHA yourself — this tool never solves CAPTCHAs\n"
                "    5. Submit the form yourself"
            ))
            for index, url in enumerate(profile.listing_urls, start=1)
        )),
        PacketSection("Confirm by email", (
            ("Verification link", (
                "Spokeo emails a confirmation link to your contact email for EACH request. "
                "The request is NOT processed until you click that link. Check spam/junk."
            )),
        )),
        PacketSection("Keep in mind", (
            ("Reappearance", (
                "Listings can reappear as Spokeo ingests new data. Re-check quarterly and "
                "repeat this flow for any new listing URLs."
            )),
        )),
    ]
    return tuple(sections)


def run_spokeo_submission(
    store: TaskStore,
    task_id: str,
    profile_path: str | Path,
    *,
    prompt_fn: Callable[[str], str] | None = None,
    out: Callable[[str], None] = print,
) -> TaskRecord:
    """Build the Spokeo packet from the owner profile and run the guided flow.

    A DISCOVERED task moves to READY_FOR_REVIEW once a valid profile (at least
    one listing URL) exists; the typed gate then records SUBMITTED_BY_OWNER.
    """
    profile = load_profile(profile_path)
    packet = build_packet(profile)
    return run_guided_flow(
        store, task_id, packet, source_name="Spokeo opt-out",
        allow_discovered=True, prompt_fn=prompt_fn, out=out,
    )
