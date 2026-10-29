import pytest

from docubye.sources.google_search_contact import (
    ContactInfoType,
    GoogleContactRemovalDraft,
    approve_google_review,
)


def valid_draft(**changes):
    values = {
        "contact_info_type": ContactInfoType.EMAIL,
        "exposed_value": "alex@example.test",
        "content_urls": ("https://example.com/profile",),
        "search_result_urls": ("https://www.google.com/search?q=Alex+Example",),
        "search_terms": ("Alex Example email",),
        "country_of_residence": "United States",
        "contact_email": "alex@example.test",
        "requester_name": "Alex Example",
        "additional_context": "",
    }
    values.update(changes)
    return GoogleContactRemovalDraft(**values)


def test_draft_validation_and_review_include_exact_data_for_user_review():
    draft = valid_draft()
    review = draft.build_review()
    assert review.destination == "https://support.google.com/websearch/contact/content_removal_form?hl=en"
    assert review.contact_info_type is ContactInfoType.EMAIL
    assert review.exposed_value == "alex@example.test"
    assert review.content_urls == ("https://example.com/profile",)
    assert review.search_result_urls == ("https://www.google.com/search?q=Alex+Example",)
    assert review.search_terms == ("Alex Example email",)


def test_redacted_audit_record_excludes_values_urls_and_search_terms():
    draft = valid_draft()
    audit = draft.redacted_audit_record()
    serialized = repr(audit)
    assert audit["contact_info_type"] == "email"
    assert audit["content_url_count"] == 1
    assert "alex@example.test" not in serialized
    assert "example.com" not in serialized
    assert "Alex Example email" not in serialized


@pytest.mark.parametrize("category", ["government_id", "bank_account", "credentials", "other"])
def test_first_source_contract_refuses_out_of_scope_categories(category):
    with pytest.raises(ValueError, match="supported contact-info category"):
        valid_draft(contact_info_type=category).validate()


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "http://localhost:8080/profile",
        "http://127.0.0.1/profile",
        "http://192.168.1.2/profile",
        "https://user:password@example.com/profile",
    ],
)
def test_content_url_rejects_invalid_or_local_destinations(url):
    with pytest.raises(ValueError):
        valid_draft(content_urls=(url,)).validate()


@pytest.mark.parametrize(
    "url",
    [
        "https://evilgoogle.com/search?q=Alex",
        "https://www.google.com.evil.test/search?q=Alex",
        "http://www.google.com/search?q=Alex",
        "https://www.google.com/maps?q=Alex",
        "https://www.google.com/search",
    ],
)
def test_search_results_url_must_be_a_google_search_results_page(url):
    with pytest.raises(ValueError, match="Google Search results page"):
        valid_draft(search_result_urls=(url,)).validate()


def test_approval_requires_all_explicit_confirmations():
    review = valid_draft().build_review()
    with pytest.raises(PermissionError, match="All three confirmations"):
        approve_google_review(
            review,
            accuracy_confirmed=True,
            authority_confirmed=True,
            search_delisting_understood=False,
        )


def test_approval_is_bound_to_exact_payload_and_can_only_be_used_once():
    draft = valid_draft()
    review = draft.build_review()
    approval = approve_google_review(
        review,
        accuracy_confirmed=True,
        authority_confirmed=True,
        search_delisting_understood=True,
    )
    changed = valid_draft(exposed_value="changed@example.test")
    with pytest.raises(PermissionError, match="changed after review"):
        approval.consume_once(changed)

    approval.consume_once(draft)
    with pytest.raises(PermissionError, match="already been used"):
        approval.consume_once(draft)


def test_review_fingerprint_is_stable_for_the_same_request():
    first = valid_draft()
    second = valid_draft()
    assert first.fingerprint() == second.fingerprint()
    assert len(first.fingerprint()) == 64
