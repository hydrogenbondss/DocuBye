import os

import pytest

from docubye.agent import MockRemovalAgent, validate_local_base_url
from docubye.mock_site import running_mock_site
from docubye.models import SyntheticProfile, TaskStatus

pytest.importorskip("playwright")


def run_if_browser_available(base_url, profile, approval, planner=None):
    agent = MockRemovalAgent(planner=planner, headless=True)
    try:
        return agent.run(base_url, profile, approval)
    except Exception as exc:
        if "Executable doesn't exist" in str(exc) or "Please run the following command" in str(exc):
            pytest.skip("Playwright-managed Chromium is not installed; CI installs it")
        if os.getenv("DOCUBYE_CHROMIUM_EXECUTABLE") and "ERR_BLOCKED_BY_ADMINISTRATOR" in str(exc):
            pytest.skip("This execution environment blocks Chromium loopback navigation; CI runs Playwright-managed Chromium")
        raise


def test_loopback_url_validation_blocks_external_origins():
    assert validate_local_base_url("http://127.0.0.1:8123") == "http://127.0.0.1:8123"
    with pytest.raises(ValueError, match="127.0.0.1"):
        validate_local_base_url("http://localhost:8123")
    with pytest.raises(ValueError, match="127.0.0.1"):
        validate_local_base_url("http://127.0.0.2:8123")
    with pytest.raises(ValueError, match="127.0.0.1"):
        validate_local_base_url("https://example.com")
    with pytest.raises(ValueError, match="127.0.0.1"):
        validate_local_base_url("http://example.com")
    with pytest.raises(ValueError, match="explicit port"):
        validate_local_base_url("http://127.0.0.1")
    with pytest.raises(ValueError, match="origin"):
        validate_local_base_url("http://127.0.0.1:8123/opt-out")


def test_user_rejection_does_not_submit():
    with running_mock_site() as (base_url, state):
        result = run_if_browser_available(base_url, SyntheticProfile(), lambda review: False)
        assert result.task.status is TaskStatus.REJECTED
        assert state.submission_count == 0
        assert result.review is not None
        assert result.review.data_categories == ("full_name", "email", "phone")


def test_approval_submits_but_does_not_claim_removal():
    with running_mock_site("normal") as (base_url, state):
        result = run_if_browser_available(base_url, SyntheticProfile(), lambda review: True)
        assert result.task.status is TaskStatus.AWAITING_CONFIRMATION
        assert state.submission_count == 1
        assert state.last_submitted_fields == SyntheticProfile().values()
        assert "not verified" in result.message.casefold()


def test_separate_mock_verification_can_mark_verified():
    with running_mock_site("verified") as (base_url, state):
        result = run_if_browser_available(base_url, SyntheticProfile(), lambda review: True)
        assert result.task.status is TaskStatus.VERIFIED_REMOVED
        assert state.submission_count == 1
        assert "simulated test evidence" in result.message


@pytest.mark.parametrize("scenario", ["challenge", "unexpected"])
def test_human_or_out_of_scope_steps_pause_before_submission(scenario):
    with running_mock_site(scenario) as (base_url, state):
        result = run_if_browser_available(base_url, SyntheticProfile(), lambda review: True)
        assert result.task.status is TaskStatus.AWAITING_USER
        assert state.submission_count == 0


@pytest.mark.parametrize("scenario", ["external-request", "external-redirect", "external-popup", "external-frame"])
def test_external_navigation_paths_are_blocked_and_require_review(scenario):
    with running_mock_site(scenario) as (base_url, state):
        result = run_if_browser_available(base_url, SyntheticProfile(), lambda review: True)
        assert result.task.status is TaskStatus.AWAITING_USER
        assert "example.com" in result.blocked_hosts
        assert state.submission_count == 0


def test_early_submission_attempt_is_blocked_until_review():
    with running_mock_site("early-submit") as (base_url, state):
        result = run_if_browser_available(base_url, SyntheticProfile(), lambda review: None)
        assert result.task.status is TaskStatus.AWAITING_USER
        assert state.submission_count == 0
        assert result.blocked_submission_attempts >= 1
        assert any("no active one-time approval" in item for item in result.blocked_requests)


def test_form_with_changed_action_is_rejected_before_approval():
    with running_mock_site("bad-form-action") as (base_url, state):
        result = run_if_browser_available(base_url, SyntheticProfile(), lambda review: True)
        assert result.task.status is TaskStatus.AWAITING_USER
        assert state.submission_count == 0
        assert result.review is None


def test_post_approval_script_cannot_reuse_submission_permission():
    with running_mock_site("duplicate-after-submit") as (base_url, state):
        result = run_if_browser_available(base_url, SyntheticProfile(), lambda review: True)
        assert result.task.status is TaskStatus.AWAITING_CONFIRMATION
        assert state.submission_count == 1
        assert result.blocked_submission_attempts >= 1


def test_form_cannot_mutate_reviewed_payload_before_submission():
    with running_mock_site("mutate-before-submit") as (base_url, state):
        result = run_if_browser_available(base_url, SyntheticProfile(), lambda review: True)
        assert result.task.status is TaskStatus.FAILED
        assert state.submission_count == 0
        assert result.blocked_submission_attempts >= 1
        assert any("payload differs" in item for item in result.blocked_requests)


def test_real_profile_values_are_rejected_before_browser_launch():
    profile = SyntheticProfile(full_name="A real person's name")
    with pytest.raises(ValueError, match="real personal data is not supported"):
        MockRemovalAgent().run("http://127.0.0.1:1", profile, lambda review: True)
