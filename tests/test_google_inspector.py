import pytest

from docubye.google_inspect import (
    EXPECTED_CONTACT_STEPS,
    InspectionReport,
    _perform_human_handoff,
    _safe_report_url,
    inspection_request_allowed,
    websocket_inspection_allowed,
)


@pytest.mark.parametrize(
    "url,method,expected",
    [
        ("https://support.google.com/websearch/contact/content_removal_form?hl=en", "GET", True),
        ("https://support.google.com/websearch/contact/content_removal_form?hl=en", "HEAD", True),
        ("https://www.google.com/search?q=example", "GET", True),
        ("https://www.gstatic.com/s2/branding/product/1x/googlelogo.png", "GET", True),
        ("https://support.google.com/websearch/contact/content_removal_form", "POST", False),
        ("https://support.google.com/websearch/contact/content_removal_form", "PUT", False),
        ("https://support.google.com/websearch/contact/content_removal_form", "PATCH", False),
        ("https://support.google.com/websearch/contact/content_removal_form/submit", "GET", False),
        ("https://support.google.com/websearch/contact/content_removal_form/formResponse", "GET", False),
        ("https://support.google.com/websearch/contact/content_removal_form/send", "GET", False),
        ("https://support.google.com/websearch/contact/content_removal_form/sendreport", "GET", False),
        ("https://accounts.google.com/signin", "GET", False),
        ("http://support.google.com/websearch/contact/content_removal_form", "GET", False),
        ("https://example.com/redirect", "GET", False),
        ("https://evilgoogle.com/search?q=example", "GET", False),
        ("https://user:secret@support.google.com/form", "GET", False),
        ("https://support.google.com:8443/form", "GET", False),
        ("https://support.google.com/websearch/contact/content_removal_form", "DELETE", False),
    ],
)
def test_inspection_network_policy(url, method, expected):
    assert inspection_request_allowed(url, method) is expected


def test_websockets_are_never_enabled_for_inspection():
    assert websocket_inspection_allowed("wss://support.google.com/socket") is False
    assert websocket_inspection_allowed("wss://example.com/socket") is False


def test_report_urls_drop_query_strings_and_fragments():
    assert _safe_report_url(
        "https://support.google.com/form?email=private@example.test#access_token=secret"
    ) == "https://support.google.com/form"


def test_inspector_selects_only_visible_exact_labels_and_never_reads_values():
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    from docubye.google_inspect import _click_unique_visible_text, _visible_field_metadata

    html = """<!doctype html>
    <html><body>
      <label><input id="personal" type="radio" name="kind">Content contains your personal information</label>
      <section id="contact" hidden>
        <label><input id="contact-info" type="radio" name="info">Address, phone number, and/or e-mail address</label>
        <label for="email">Contact email</label>
        <input id="email" name="contact_email" type="email" value="not-for-logging@example.test" required>
        <label for="url">Specific content URL</label>
        <input id="url" name="content_url" type="url" placeholder="https://example.test" required>
        <button type="button">Next</button>
        <button type="submit">Submit</button>
      </section>
      <script>
        document.querySelector("#personal").addEventListener("change", () => {
          document.querySelector("#contact").hidden = false;
        });
      </script>
    </body></html>"""

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)
        assert _click_unique_visible_text(page, "Content contains your personal information") is True
        assert page.locator("#personal").is_checked()
        assert _click_unique_visible_text(page, "Address, phone number, and/or e-mail address") is True
        assert page.locator("#contact-info").is_checked()
        fields, buttons = _visible_field_metadata(page)
        assert {field.element_id for field in fields} >= {"personal", "contact-info", "email", "url"}
        assert {field.name for field in fields} >= {"kind", "info", "contact_email", "content_url"}
        assert buttons == ["Next", "Submit"]
        assert all(not hasattr(field, "value") for field in fields)
        assert "not-for-logging@example.test" not in repr(fields)
        assert page.locator("#email").input_value() == "not-for-logging@example.test"
        browser.close()


def test_inspector_refuses_ambiguous_visible_label():
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    from docubye.google_inspect import _click_unique_visible_text

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("<button>Continue</button><a href='#'>Continue</a>")
        assert _click_unique_visible_text(page, "Continue") is False
        browser.close()


def test_inspector_stops_before_branch_selection_when_captcha_is_visible():
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    from docubye.google_inspect import _safe_to_inspect_without_handoff

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<label><input id="personal" type="radio">Content contains your personal information</label>'
            '<iframe title="reCAPTCHA" src="about:blank" width="304" height="78"></iframe>'
        )
        assert _safe_to_inspect_without_handoff(page) is False
        assert page.locator("#personal").is_checked() is False
        browser.close()


def test_inspector_does_not_treat_hidden_captcha_as_visible_challenge():
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    from docubye.google_inspect import _verification_challenge_visible

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<div class="g-recaptcha" style="display:none" data-sitekey="synthetic"></div>'
        )
        assert _verification_challenge_visible(page) is False
        browser.close()


def test_human_handoff_records_only_metadata_and_selected_choice_labels():
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    html = """<!doctype html>
    <html><body>
      <label><input type="radio" checked name="kind" value="private">Content contains your personal information</label>
      <label><input type="radio" checked name="info" value="secret">Address, phone number, and/or e-mail address</label>
      <label for="contact">Contact email</label>
      <input id="contact" name="contact_email" value="must-never-appear@example.test">
      <button type="button">Next</button>
      <button type="submit">Submit</button>
    </body></html>"""

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)
        report = InspectionReport(start_url="https://support.google.com/form")
        report.blocked_requests.append(
            {"method": "POST", "host": "support.google.com", "path": "/form"}
        )
        prompts = []
        _perform_human_handoff(page, report, lambda message: prompts.append(message) or "")

        assert report.human_handoff_offered is True
        assert report.human_handoff_used is True
        assert report.verification_challenge_detected is False
        assert report.selected_steps == EXPECTED_CONTACT_STEPS
        assert {field.name for field in report.visible_fields} >= {"kind", "info", "contact_email"}
        assert report.visible_buttons == ["Next", "Submit"]
        assert "must-never-appear@example.test" not in repr(report)
        assert "GET/HEAD" in prompts[0]
        assert "do NOT sign in" in prompts[0]
        assert any("1 request(s) were blocked" in note for note in report.notes)
        assert report.submitted is False
        assert report.filled_fields is False
        browser.close()


def test_human_handoff_reports_a_captcha_that_remains_visible():
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<iframe title="reCAPTCHA" src="about:blank" width="304" height="78"></iframe>'
        )
        report = InspectionReport(start_url="https://support.google.com/form")
        _perform_human_handoff(page, report, lambda _message: "")
        assert report.verification_challenge_detected is True
        assert report.verification_challenge_resolved is False
        assert any("remains visible" in note for note in report.notes)
        browser.close()


def test_human_handoff_marks_only_a_previously_visible_challenge_as_resolved():
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<iframe id="challenge" title="reCAPTCHA" src="about:blank" width="304" height="78"></iframe>'
        )
        report = InspectionReport(start_url="https://support.google.com/form")

        def operator_clears_challenge(_message):
            page.locator("#challenge").evaluate("(el) => el.remove()")
            return ""

        _perform_human_handoff(page, report, operator_clears_challenge)
        assert report.verification_challenge_detected is True
        assert report.verification_challenge_resolved is True
        browser.close()


def test_human_handoff_requires_visible_browser():
    from docubye.google_inspect import inspect_google_contact_form

    with pytest.raises(ValueError, match="requires a visible browser"):
        inspect_google_contact_form(headless=True, human_handoff=True)


def test_human_handoff_reports_a_challenge_that_appears_during_observation():
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("<html><body><p>Initial page</p></body></html>")
        report = InspectionReport(start_url="https://support.google.com/form")

        def operator_sees_new_challenge(_message):
            page.set_content(
                '<iframe title="reCAPTCHA" src="about:blank" width="304" height="78"></iframe>'
            )
            return ""

        _perform_human_handoff(page, report, operator_sees_new_challenge)
        assert report.verification_challenge_detected is True
        assert report.verification_challenge_resolved is False
        browser.close()


def test_cli_requires_headed_mode_for_human_handoff(monkeypatch):
    import sys
    from docubye.google_inspect import main

    monkeypatch.setattr(sys, "argv", ["docubye-inspect-google-form", "--human-handoff"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_cli_requires_an_interactive_terminal_for_human_handoff(monkeypatch):
    import sys
    from types import SimpleNamespace
    from docubye.google_inspect import main

    monkeypatch.setattr(
        sys, "argv", ["docubye-inspect-google-form", "--headed", "--human-handoff"]
    )
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: False))
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
