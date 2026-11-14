import json
from pathlib import Path

import pytest

from docubye.google_inspect import EXPECTED_CONTACT_STEPS
from docubye.sources.google import FORM_PATH, serve_google_fixtures
from docubye.sources.google_capture import (
    ACCOUNT_CONFIRMATION,
    redaction_diff,
    run_capture,
    sanitize_html,
    validate_selectors,
)

pytest.importorskip("playwright")

PLANTED = {
    "email": "jane.doe@example.com",
    "phone": "+1 415 555 0132",
    "token": "sid=abc123sessiontoken",
    "name": "Jane Doe",
}

PII_PAGE = """<!doctype html>
<html><body>
  <div aria-label="Google Account: Jane Doe (jane.doe@example.com)" data-ogpc>Jane Doe</div>
  <img src="https://lh3.googleusercontent.com/avatar-photo" alt="Jane Doe">
  <a href="https://support.google.com/websearch/contact/content_removal_form?sid=abc123sessiontoken&hl=en">form</a>
  <p>Call +1 415 555 0132 or email jane.doe@example.com</p>
</body></html>"""


def test_sanitize_html_strips_planted_fake_pii():
    sanitized, applied = sanitize_html(PII_PAGE)
    assert applied  # something was redacted
    for forbidden in PLANTED.values():
        assert forbidden not in sanitized
    assert "abc123sessiontoken" not in sanitized
    assert "[redacted-email]" in sanitized
    assert "[redacted-phone]" in sanitized
    assert "[redacted-param]" in sanitized
    assert "[redacted-avatar]" in sanitized


def test_redaction_diff_shows_only_changed_hunks():
    sanitized, _ = sanitize_html(PII_PAGE)
    diff = redaction_diff(PII_PAGE, sanitized)
    assert "[redacted-email]" in diff
    assert "jane.doe@example.com" in diff  # visible to the operator BEFORE saving
    assert "---" in diff and "+++" in diff


def test_validate_selectors_reports_found_missing_ambiguous(chromium):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            f"<label><input type='radio'>{EXPECTED_CONTACT_STEPS[0]}</label>"
            "<button>Next</button><button>Next</button>"
        )
        checks = {(c.description): c.status for c in validate_selectors(page, "test-step")}
        assert checks[f"text:{EXPECTED_CONTACT_STEPS[0]}"] == "found"
        assert checks[f"text:{EXPECTED_CONTACT_STEPS[1]}"] == "missing"
        assert checks["button:Next"] == "ambiguous"
        assert checks["button:Submit"] == "missing"
        assert checks["captcha-or-challenge"] == "missing"
        assert all(c.step == "test-step" for c in validate_selectors(page, "test-step"))
        browser.close()


def test_capture_refuses_without_env_opt_in():
    with pytest.raises(RuntimeError, match="DOCUBYE_REAL_SOURCE"):
        run_capture(env={}, prompt_fn=lambda _message: "")


def test_capture_refuses_without_typed_account_confirmation():
    with pytest.raises(PermissionError, match="account confirmation"):
        run_capture(env={"DOCUBYE_REAL_SOURCE": "1"}, prompt_fn=lambda _message: "yes sure")


def _scripted_prompts(answers):
    iterator = iter(answers)
    return lambda _message: next(iterator, "")


def test_offline_capture_flow_sanitizes_and_reports(chromium, tmp_path):
    # Fixture page with planted fake PII layered onto the happy wizard.
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    html = Path("tests/fixtures/google/happy.html").read_text(encoding="utf-8").replace(
        "</main>",
        f'<div aria-label="Google Account: Jane Doe (jane.doe@example.com)" data-ogpc>Jane Doe</div>'
        f'<p>Contact jane.doe@example.com or +1 415 555 0132</p></main>',
    )
    (fixture_dir / "happy.html").write_text(html, encoding="utf-8")

    with serve_google_fixtures(fixture_dir, "happy") as (base, counts):
        prompts = _scripted_prompts([
            ACCOUNT_CONFIRMATION,  # account confirmation
            "",                    # sign-in pause (fixture needs none)
            "save", "save", "save",
        ])
        result = run_capture(
            output_dir=tmp_path / "captures",
            start_url=f"{base}{FORM_PATH}?hl=en",
            allow_request=lambda url, method: url.startswith(base) and method.upper() == "GET",
            prompt_fn=prompts,
            env={"DOCUBYE_REAL_SOURCE": "1"},
            headless=True,
        )
        assert counts["posts"] == 0

    assert len(result.saved_files) == 3
    for saved in result.saved_files:
        content = Path(saved).read_text(encoding="utf-8")
        assert "jane.doe@example.com" not in content
        assert "Jane Doe" not in content
        assert "+1 415 555 0132" not in content

    report = result.report()
    landing = {(c["selector"]): c["status"] for c in report["selector_checks"] if c["step"] == "landing"}
    contact = {(c["selector"]): c["status"] for c in report["selector_checks"] if c["step"] == "contact-branch"}
    assert landing[f"text:{EXPECTED_CONTACT_STEPS[0]}"] == "found"
    assert contact[f"text:{EXPECTED_CONTACT_STEPS[1]}"] == "found"
    assert "Submit" not in json.dumps(report["notes"])
    assert any("No fields were filled" in note for note in report["notes"])


def test_capture_declined_save_writes_nothing(chromium, tmp_path):
    with serve_google_fixtures("tests/fixtures/google", "happy") as (base, _counts):
        prompts = _scripted_prompts([ACCOUNT_CONFIRMATION, "", "no", "no", "no"])
        result = run_capture(
            output_dir=tmp_path / "captures",
            start_url=f"{base}{FORM_PATH}?hl=en",
            allow_request=lambda url, method: url.startswith(base) and method.upper() == "GET",
            prompt_fn=prompts,
            env={"DOCUBYE_REAL_SOURCE": "1"},
            headless=True,
        )
    assert result.saved_files == []
    assert not (tmp_path / "captures").exists()
    assert any("declined" in note for note in result.notes)
