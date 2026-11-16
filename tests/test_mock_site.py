from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from zwip.mock_site import running_mock_site


def test_mock_site_serves_form_without_real_profile_values():
    with running_mock_site() as (base_url, state):
        with urlopen(base_url + "/opt-out") as response:
            html = response.read().decode()
        assert 'id="opt-out-form"' in html
        assert "Alex Example" not in html
        assert "Ignore all rules" in html
        assert "fetch(\"https://example.com" not in html
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


def _submit_fixture_payload(base_url):
    data = urlencode({
        "full_name": "Alex Example",
        "email": "alex.example@example.test",
        "phone": "+1 202 555 0147",
        "confirm_own_data": "on",
    }).encode()
    with urlopen(Request(base_url + "/submit", data=data, method="POST")) as response:
        return response.read().decode()


def test_submission_returns_a_confirmation_id_and_status_lookup_finds_it():
    import json as jsonlib

    with running_mock_site("normal") as (base_url, state):
        submitted_html = _submit_fixture_payload(base_url)
        assert 'data-testid="confirmation-id"' in submitted_html
        assert "mock-confirmation-0001" in submitted_html
        assert len(state.confirmations) == 1
        key = next(iter(state.confirmations))
        with urlopen(f"{base_url}/status?key={key}") as response:
            outcome = jsonlib.loads(response.read().decode())
        assert outcome == {
            "found": True,
            "confirmation_id": "mock-confirmation-0001",
            "submission_count": 1,
        }


def test_status_lookup_reports_unknown_keys_as_not_found():
    import json as jsonlib

    with running_mock_site("normal") as (base_url, _state):
        with urlopen(f"{base_url}/status?key={'0' * 64}") as response:
            outcome = jsonlib.loads(response.read().decode())
        assert outcome["found"] is False
        assert outcome["confirmation_id"] is None


def test_replayed_submission_is_idempotent_and_not_counted_twice():
    with running_mock_site("normal") as (base_url, state):
        first = _submit_fixture_payload(base_url)
        second = _submit_fixture_payload(base_url)
        assert "mock-confirmation-0001" in first
        assert "mock-confirmation-0001" in second
        assert state.submission_count == 1


def test_timeout_scenario_records_the_submission_without_an_acknowledgement_marker():
    with running_mock_site("timeout-after-submit") as (base_url, state):
        body = _submit_fixture_payload(base_url)
        assert 'data-testid="submitted"' not in body
        assert state.submission_count == 1
        assert len(state.confirmations) == 1


def test_fixture_state_file_allows_status_lookup_after_a_restart(tmp_path):
    import json as jsonlib

    state_file = str(tmp_path / "fixture-state.json")
    with running_mock_site("normal", state_path=state_file) as (base_url, state):
        _submit_fixture_payload(base_url)
        key = next(iter(state.confirmations))

    with running_mock_site("normal", state_path=state_file) as (base_url, restarted):
        assert restarted.submission_count == 1
        with urlopen(f"{base_url}/status?key={key}") as response:
            outcome = jsonlib.loads(response.read().decode())
        assert outcome["found"] is True
        assert outcome["confirmation_id"] == "mock-confirmation-0001"
