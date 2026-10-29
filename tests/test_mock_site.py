from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from docubye.mock_site import running_mock_site


def test_mock_site_serves_form_without_real_profile_values():
    with running_mock_site() as (base_url, state):
        with urlopen(base_url + "/opt-out") as response:
            html = response.read().decode()
        assert 'id="opt-out-form"' in html
        assert "Alex Example" not in html
        assert "https://example.com" in html
        assert state.submission_count == 0


def test_submission_acknowledgement_is_not_deletion_verification():
    with running_mock_site("normal") as (base_url, state):
        data = urlencode({
            "full_name": "Alex Example",
            "email": "alex.example@example.test",
            "phone": "+1 202 555 0147",
            "confirm_own_data": "on",
        }).encode()
        request = Request(base_url + "/submit", data=data, method="POST")
        with urlopen(request) as response:
            submitted_html = response.read().decode()
        with urlopen(base_url + "/verify") as response:
            verification_html = response.read().decode()
        assert "Request received" in submitted_html
        assert "not confirmation of deletion" in submitted_html
        assert "Awaiting confirmation" in verification_html
        assert state.submission_count == 1
        assert state.last_submitted_fields["email"] == "alex.example@example.test"


def test_fixture_verifies_only_the_explicit_verified_scenario():
    with running_mock_site("verified") as (base_url, state):
        data = urlencode({
            "full_name": "Alex Example",
            "email": "alex.example@example.test",
            "phone": "+1 202 555 0147",
            "confirm_own_data": "on",
        }).encode()
        urlopen(Request(base_url + "/submit", data=data, method="POST")).close()
        with urlopen(base_url + "/verify") as response:
            body = response.read().decode()
        assert "Removal verified" in body


def test_fixture_rejects_unknown_scenario():
    with pytest.raises(ValueError, match="Unsupported mock scenario"):
        with running_mock_site("production"):
            pass
