import json
from pathlib import Path

import pytest

from zwip.google_inspect import EXPECTED_CONTACT_STEPS
from zwip.sources.google import FORM_PATH, serve_google_fixtures
from zwip.sources.google_capture import (
    ACCOUNT_CONFIRMATION,
    redaction_diff,
    run_capture,
    sanitize_html,
    signin_phase_allowed,
    validate_selectors,
    wizard_phase_allowed,
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
        checks = {c.description: (c.status, c.visibility) for c in validate_selectors(page, "test-step")}
        assert checks[f"text:{EXPECTED_CONTACT_STEPS[0]}"] == ("found", "visible")
        assert checks[f"text:{EXPECTED_CONTACT_STEPS[1]}"] == ("missing", "absent")
        assert checks["button:Next"] == ("ambiguous", "visible")
        assert checks["button:Submit"] == ("missing", "absent")
        assert checks["captcha-or-challenge"][0] == "missing"
        assert all(c.step == "test-step" for c in validate_selectors(page, "test-step"))
        browser.close()


def test_hidden_but_present_selector_counts_as_found(chromium):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        # The real wizard keeps conditional sections in the DOM before revealing them.
        page.set_content(
            f'<fieldset hidden><label><input type="radio">{EXPECTED_CONTACT_STEPS[1]}</label>'
            '<label for="id-last-four">Last four characters of the ID</label>'
            '<input id="id-last-four" name="id_last_four" type="text"></fieldset>'
        )
        checks = {c.description: (c.status, c.visibility) for c in validate_selectors(page, "test-step")}
        assert checks[f"text:{EXPECTED_CONTACT_STEPS[1]}"] == ("found", "hidden")
        assert checks["text:Last four characters of the ID"] == ("found", "hidden")
        browser.close()


def test_signin_phase_policy_allows_human_auth_posts_and_blocks_telemetry():
    # The human's own sign-in form submission passes during the sign-in phase.
    assert signin_phase_allowed("https://accounts.google.com/signin/v2/challenge", "POST")
    assert signin_phase_allowed("https://accounts.google.com/ServiceLogin", "GET")
    # Wizard and static hosts stay read-only even in the sign-in phase.
    assert not signin_phase_allowed("https://support.google.com/websearch/contact/x", "POST")
    assert signin_phase_allowed("https://support.google.com/websearch/contact/x", "GET")
    assert signin_phase_allowed("https://www.gstatic.com/script.js", "GET")
    # Telemetry and look-alike or plaintext auth hosts stay blocked.
    assert not signin_phase_allowed("https://play.google.com/log", "POST")
    assert not signin_phase_allowed("https://www.google-analytics.com/collect", "POST")
    assert not signin_phase_allowed("https://accounts.google.com.evil.test/", "POST")
    assert not signin_phase_allowed("http://accounts.google.com/signin", "POST")


def test_wizard_phase_policy_relocks_to_read_only():
    assert wizard_phase_allowed("https://support.google.com/websearch/contact/x", "GET")
    assert wizard_phase_allowed("https://www.gstatic.com/script.js", "HEAD")
    assert not wizard_phase_allowed("https://support.google.com/websearch/contact/x", "POST")
    # The auth host itself is no longer reachable once the wizard phase begins.
    assert not wizard_phase_allowed("https://accounts.google.com/signin", "POST")
    assert not wizard_phase_allowed("https://accounts.google.com/signin", "GET")
    assert not wizard_phase_allowed("https://play.google.com/log", "GET")


def test_capture_refuses_without_env_opt_in():
    with pytest.raises(RuntimeError, match="ZWIP_REAL_SOURCE"):
        run_capture(env={}, prompt_fn=lambda _message: "")


def test_capture_refuses_without_typed_account_confirmation():
    with pytest.raises(PermissionError, match="account confirmation"):
        run_capture(env={"ZWIP_REAL_SOURCE": "1"}, prompt_fn=lambda _message: "yes sure")


def _scripted_prompts(answers, calls):
    iterator = iter(answers)

    def prompt(message):
        calls.append(message)
        return next(iterator, "")

    return prompt


def _offline_capture(base, tmp_path, answers, calls, **overrides):
    params = {
        "output_dir": tmp_path / "captures",
        "start_url": f"{base}{FORM_PATH}?hl=en",
        "prompt_fn": _scripted_prompts(answers, calls),
        "env": {"ZWIP_REAL_SOURCE": "1"},
        "headless": True,
        "live": False,
        "auth_host": "127.0.0.1",
        "wizard_host": "127.0.0.1",
    }
    params.update(overrides)
    return run_capture(**params)


def test_offline_capture_flow_sanitizes_and_reports(chromium, tmp_path):
    # Fixture page with planted fake PII layered onto the happy wizard.
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    html = Path("tests/fixtures/google/happy.html").read_text(encoding="utf-8").replace(
        "</main>",
        '<div aria-label="Google Account: Jane Doe (jane.doe@example.com)" data-ogpc>Jane Doe</div>'
        '<p>Contact jane.doe@example.com or +1 415 555 0132</p></main>',
    )
    (fixture_dir / "happy.html").write_text(html, encoding="utf-8")

    calls: list[str] = []
    with serve_google_fixtures(fixture_dir, "happy") as (base, counts):
        result = _offline_capture(
            base, tmp_path,
            [ACCOUNT_CONFIRMATION, "", "save", "save", "save"],
            calls,
        )
        assert counts["posts"] == 0

    assert len(result.saved_files) == 3
    for saved in result.saved_files:
        content = Path(saved).read_text(encoding="utf-8")
        assert "jane.doe@example.com" not in content
        assert "Jane Doe" not in content
        assert "+1 415 555 0132" not in content

    report = result.report()
    landing = {(c["selector"]): (c["status"], c["visibility"]) for c in report["selector_checks"] if c["step"] == "landing"}
    contact = {(c["selector"]): (c["status"], c["visibility"]) for c in report["selector_checks"] if c["step"] == "contact-branch"}
    assert landing[f"text:{EXPECTED_CONTACT_STEPS[0]}"] == ("found", "visible")
    # The info-type branch exists in the DOM but is hidden until the reason radio is selected.
    assert landing[f"text:{EXPECTED_CONTACT_STEPS[1]}"] == ("found", "hidden")
    assert contact[f"text:{EXPECTED_CONTACT_STEPS[1]}"] == ("found", "visible")
    # The conditional government-ID sub-section stays hidden when not selected.
    assert contact["text:Last four characters of the ID"] == ("found", "hidden")
    assert "Submit" not in json.dumps(report["notes"])
    assert any("No fields were filled" in note for note in report["notes"])


def test_capture_declined_save_writes_nothing(chromium, tmp_path):
    calls: list[str] = []
    with serve_google_fixtures("tests/fixtures/google", "happy") as (base, _counts):
        result = _offline_capture(
            base, tmp_path, [ACCOUNT_CONFIRMATION, "", "no", "no", "no"], calls
        )
    assert result.saved_files == []
    assert not (tmp_path / "captures").exists()
    assert any("declined" in note for note in result.notes)


def test_signin_phase_allows_auth_post_but_blocks_telemetry(chromium, tmp_path):
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    html = Path("tests/fixtures/google/happy.html").read_text(encoding="utf-8").replace(
        "</body>",
        '<script>'
        'fetch("/auth-endpoint", {method:"POST", body:"human-signin=1"}).catch(() => {});'
        'fetch("https://play.google.com/log", {method:"POST", body:"t=1"}).catch(() => {});'
        "</script></body>",
    )
    (fixture_dir / "happy.html").write_text(html, encoding="utf-8")

    calls: list[str] = []
    with serve_google_fixtures(fixture_dir, "happy") as (base, counts):
        result = _offline_capture(
            base, tmp_path, [ACCOUNT_CONFIRMATION, "", "no", "no", "no"], calls
        )
        # The human's sign-in POST passed in the sign-in phase...
        assert counts["posts"] == 1

    # ...and the telemetry POST was blocked, logged redacted (method/host/path only).
    assert any("Blocked POST play.google.com" in note for note in result.notes)
    assert "t=1" not in json.dumps(result.notes)


def test_wizard_phase_relocks_and_blocks_posts(chromium, tmp_path):
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    html = Path("tests/fixtures/google/happy.html").read_text(encoding="utf-8").replace(
        "</body>",
        '<script>'
        'fetch("/auth-endpoint", {method:"POST", body:"human-signin=1"}).catch(() => {});'
        'document.querySelectorAll(\'input[name="reason"]\').forEach(function (r) {'
        '  r.addEventListener("change", function () {'
        '    fetch("/submit-attempt", {method:"POST", body:"x=1"}).catch(() => {});'
        "  });"
        "});"
        "</script></body>",
    )
    (fixture_dir / "happy.html").write_text(html, encoding="utf-8")

    calls: list[str] = []
    with serve_google_fixtures(fixture_dir, "happy") as (base, counts):
        result = _offline_capture(
            base, tmp_path, [ACCOUNT_CONFIRMATION, "", "no", "no", "no"], calls
        )
        # Only the sign-in-phase POST reached the server; the wizard-phase POST
        # fired by the branch click was blocked after the guard re-locked.
        assert counts["posts"] == 1

    assert any("Blocked POST 127.0.0.1/submit-attempt (wizard phase)" in note for note in result.notes)
    assert any("No fields were filled" in note for note in result.notes)


def test_non_empty_handoff_input_reprompts(chromium, tmp_path):
    calls: list[str] = []
    with serve_google_fixtures("tests/fixtures/google", "happy") as (base, _counts):
        result = _offline_capture(
            base, tmp_path,
            [ACCOUNT_CONFIRMATION, "rm -rf ~", "", "no", "no", "no"],
            calls,
        )
    assert any("press Enter alone" in message for message in calls)
    assert len(result.checks) > 0  # the run proceeded only after an empty Enter


def test_wizard_not_loaded_pauses_with_redacted_note(chromium, tmp_path):
    # The page loads (auth host), but it is not the wizard domain: the run must
    # pause with a note instead of producing an empty report.
    calls: list[str] = []
    with serve_google_fixtures("tests/fixtures/google", "happy") as (base, _counts):
        result = run_capture(
            output_dir=tmp_path / "captures",
            start_url=f"{base}{FORM_PATH}?hl=en",
            prompt_fn=_scripted_prompts([ACCOUNT_CONFIRMATION, ""], calls),
            env={"ZWIP_REAL_SOURCE": "1"},
            headless=True,
            live=False,
            auth_host="127.0.0.1",
            wizard_host="support.google.com",  # not what the fixture serves
        )
    assert result.saved_files == []
    assert result.checks == []
    assert any("Wizard domain not loaded" in note for note in result.notes)


# --- Live browser-launch policy (mocked Playwright; no browser, no network) ---

class _StopCapture(Exception):
    pass


def _fake_playwright_session(monkeypatch, **launchers):
    import types

    import playwright.sync_api as sync_api

    chromium = types.SimpleNamespace(**launchers)

    class FakeSession:
        def __enter__(self):
            return types.SimpleNamespace(chromium=chromium)

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(sync_api, "sync_playwright", lambda: FakeSession())


def test_live_path_uses_real_chrome_persistent_context(monkeypatch, tmp_path):
    import playwright.sync_api as sync_api

    calls: dict = {}

    def fake_lpc(user_data_dir, **kwargs):
        calls["user_data_dir"] = str(user_data_dir)
        calls.update(kwargs)
        raise sync_api.Error("stop after recording launch arguments")

    _fake_playwright_session(monkeypatch, launch_persistent_context=fake_lpc)
    # The harness wraps launcher errors; the recorded arguments prove the policy.
    with pytest.raises(RuntimeError, match="Google Chrome is not installed") as excinfo:
        run_capture(
            env={"ZWIP_REAL_SOURCE": "1"},
            prompt_fn=lambda _message: ACCOUNT_CONFIRMATION,
            output_dir=tmp_path / "captures" / "google",
        )
    assert "stop after recording" in str(excinfo.value.__cause__)
    assert calls["channel"] == "chrome"
    assert calls["headless"] is False
    assert calls["user_data_dir"].endswith("chrome-profile")
    assert "captures" in calls["user_data_dir"]


def test_live_path_reports_missing_chrome_clearly(monkeypatch, tmp_path):
    import playwright.sync_api as sync_api

    def fake_lpc(user_data_dir, **kwargs):
        raise sync_api.Error("Executable doesn't exist")

    _fake_playwright_session(monkeypatch, launch_persistent_context=fake_lpc)
    with pytest.raises(RuntimeError, match="Google Chrome is not installed"):
        run_capture(
            env={"ZWIP_REAL_SOURCE": "1"},
            prompt_fn=lambda _message: ACCOUNT_CONFIRMATION,
            output_dir=tmp_path / "captures",
        )


def test_fixture_path_keeps_playwright_chromium(monkeypatch, tmp_path):
    calls: dict = {}

    def fake_launch(**kwargs):
        calls["launch"] = kwargs
        raise _StopCapture()

    def fake_lpc(user_data_dir, **kwargs):
        calls["persistent"] = True
        raise _StopCapture()

    _fake_playwright_session(
        monkeypatch, launch=fake_launch, launch_persistent_context=fake_lpc
    )
    with pytest.raises(_StopCapture):
        run_capture(
            env={"ZWIP_REAL_SOURCE": "1"},
            prompt_fn=lambda _message: ACCOUNT_CONFIRMATION,
            output_dir=tmp_path / "captures",
            start_url="http://127.0.0.1:9/websearch/contact/content_removal_form?hl=en",
            headless=True,
            live=False,
        )
    assert calls["launch"] == {"headless": True}
    assert "persistent" not in calls


def test_live_path_refuses_headless(monkeypatch, tmp_path):
    _fake_playwright_session(monkeypatch)
    with pytest.raises(ValueError, match="headed browser"):
        run_capture(
            env={"ZWIP_REAL_SOURCE": "1"},
            prompt_fn=lambda _message: ACCOUNT_CONFIRMATION,
            output_dir=tmp_path / "captures",
            headless=True,  # start_url defaults to the live URL
        )
