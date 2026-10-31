"""Preflight contract for Google's personal-contact-information Search-removal form.

This module prepares and validates a request for review. It deliberately does not
navigate to Google or submit a request. A live browser adapter remains blocked
until the active form branch has been inspected and its selectors verified.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import parse_qs, urlsplit

GOOGLE_FORM_URL = "https://support.google.com/websearch/contact/content_removal_form?hl=en"
MAX_URLS = 1000
MAX_SEARCH_TERMS = 1000
MAX_CONTEXT_CHARS = 4000
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_GOOGLE_HOST_RE = re.compile(
    r"^(?:[a-z0-9-]+\.)*google\.(?:com|[a-z]{2,3}|co\.[a-z]{2}|com\.[a-z]{2})$",
    re.IGNORECASE,
)


class ContactInfoType(StrEnum):
    ADDRESS = "address"
    PHONE = "phone"
    EMAIL = "email"


@dataclass(frozen=True, slots=True)
class GoogleContactRemovalDraft:
    """User-confirmed inputs for one contact-info category.

    Sensitive values live in memory only. Do not log or persist this object.
    The source form can change; the eventual live adapter must compare the
    observed form against this contract and pause on unsupported variations.
    """

    contact_info_type: ContactInfoType
    exposed_value: str
    content_urls: tuple[str, ...]
    search_result_urls: tuple[str, ...]
    search_terms: tuple[str, ...]
    country_of_residence: str
    contact_email: str
    requester_name: str = ""
    additional_context: str = ""

    def validate(self) -> None:
        if not isinstance(self.contact_info_type, ContactInfoType):
            raise ValueError("Choose exactly one supported contact-info category")
        if not self.exposed_value.strip():
            raise ValueError("The exposed contact value is required")
        if not self.country_of_residence.strip():
            raise ValueError("Country of residence is required")
        if not _EMAIL_RE.fullmatch(self.contact_email.strip()):
            raise ValueError("A valid contact email is required for this request draft")
        if len(self.additional_context) > MAX_CONTEXT_CHARS:
            raise ValueError(f"Additional context must be at most {MAX_CONTEXT_CHARS} characters")
        self._validate_list("content URL", self.content_urls, maximum=MAX_URLS, is_url=True)
        self._validate_list("Google Search results URL", self.search_result_urls, maximum=MAX_URLS, is_url=True)
        self._validate_list("search term", self.search_terms, maximum=MAX_SEARCH_TERMS, is_url=False)
        for value in self.search_result_urls:
            if not _is_google_search_results_url(value):
                raise ValueError("Each results URL must be a Google Search results page URL")

    @staticmethod
    def _validate_list(label: str, values: tuple[str, ...], *, maximum: int, is_url: bool) -> None:
        if not values:
            raise ValueError(f"At least one {label} is required")
        if len(values) > maximum:
            raise ValueError(f"At most {maximum} {label}s are supported")
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Every {label} must be non-empty")
            if is_url:
                _validate_http_url(value, label)
            elif len(value) > 500:
                raise ValueError("Each search term must be at most 500 characters")

    def fingerprint(self) -> str:
        """Stable digest binding approval to the exact request; never log the input fields."""
        canonical = {
            "contact_info_type": self.contact_info_type.value,
            "exposed_value": self.exposed_value.strip(),
            "content_urls": list(self.content_urls),
            "search_result_urls": list(self.search_result_urls),
            "search_terms": list(self.search_terms),
            "country_of_residence": self.country_of_residence.strip(),
            "contact_email": self.contact_email.strip(),
            "requester_name": self.requester_name.strip(),
            "additional_context": self.additional_context.strip(),
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        return hashlib.sha256(encoded).hexdigest()

    def build_review(self) -> "GoogleContactReview":
        self.validate()
        return GoogleContactReview(
            destination=GOOGLE_FORM_URL,
            contact_info_type=self.contact_info_type,
            exposed_value=self.exposed_value.strip(),
            content_urls=self.content_urls,
            search_result_urls=self.search_result_urls,
            search_terms=self.search_terms,
            country_of_residence=self.country_of_residence.strip(),
            requester_name=self.requester_name.strip(),
            contact_email=self.contact_email.strip(),
            additional_context=self.additional_context.strip(),
            request_fingerprint=self.fingerprint(),
        )

    def redacted_audit_record(self) -> dict[str, object]:
        """Safe operational metadata without raw values, URLs, email, or search terms."""
        self.validate()
        return {
            "source": "google-search-personal-contact",
            "contact_info_type": self.contact_info_type.value,
            "content_url_count": len(self.content_urls),
            "search_result_url_count": len(self.search_result_urls),
            "search_term_count": len(self.search_terms),
            "has_contact_email": bool(self.contact_email.strip()),
            "has_requester_name": bool(self.requester_name.strip()),
            "has_additional_context": bool(self.additional_context.strip()),
        }


@dataclass(frozen=True, slots=True)
class GoogleContactReview:
    """Complete review shown to the user; this object contains sensitive information."""

    destination: str
    contact_info_type: ContactInfoType
    exposed_value: str
    content_urls: tuple[str, ...]
    search_result_urls: tuple[str, ...]
    search_terms: tuple[str, ...]
    country_of_residence: str
    requester_name: str
    contact_email: str
    additional_context: str
    request_fingerprint: str


@dataclass(slots=True)
class GoogleContactApproval:
    """One-time review approval bound to the exact request fingerprint."""

    request_fingerprint: str
    accuracy_confirmed: bool
    authority_confirmed: bool
    search_delisting_understood: bool
    _consumed: bool = field(default=False, init=False, repr=False)

    def consume_once(self, draft: GoogleContactRemovalDraft) -> None:
        """Call immediately before submission; a failed or completed attempt cannot reuse approval."""
        if self._consumed:
            raise PermissionError("This Google request approval has already been used")
        # Consume first: even a malformed/mismatched attempt must not leave this
        # approval reusable for a later request.
        self._consumed = True
        if not (
            self.accuracy_confirmed
            and self.authority_confirmed
            and self.search_delisting_understood
        ):
            raise PermissionError("Accuracy, authority, and search-removal acknowledgements are required")
        draft.validate()
        if draft.fingerprint() != self.request_fingerprint:
            raise PermissionError("The request changed after review; a fresh approval is required")


def approve_google_review(
    review: GoogleContactReview,
    *,
    accuracy_confirmed: bool,
    authority_confirmed: bool,
    search_delisting_understood: bool,
) -> GoogleContactApproval:
    """Create approval only after three explicit positive confirmations."""
    if not (accuracy_confirmed and authority_confirmed and search_delisting_understood):
        raise PermissionError("All three confirmations must be explicitly accepted")
    return GoogleContactApproval(
        request_fingerprint=review.request_fingerprint,
        accuracy_confirmed=accuracy_confirmed,
        authority_confirmed=authority_confirmed,
        search_delisting_understood=search_delisting_understood,
    )


def _validate_http_url(value: str, label: str) -> None:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Each {label} must be an absolute http:// or https:// URL")
    if parsed.username or parsed.password:
        raise ValueError(f"{label} must not contain embedded credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{label} has an invalid port") from exc
    if port is not None and not (1 <= port <= 65535):
        raise ValueError(f"{label} has an invalid port")
    host = parsed.hostname.casefold().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise ValueError(f"{label} must not point to a local hostname")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
        raise ValueError(f"{label} must not point to a private or reserved IP address")


def _is_google_search_results_url(value: str) -> bool:
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme != "https" or not _GOOGLE_HOST_RE.fullmatch(host):
        return False
    if parsed.path.rstrip("/") != "/search":
        return False
    query = parse_qs(parsed.query)
    return bool(query.get("q") or query.get("as_q"))
