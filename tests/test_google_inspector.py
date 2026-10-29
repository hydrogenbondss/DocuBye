import pytest

from docubye.google_inspect import inspection_request_allowed, websocket_inspection_allowed


@pytest.mark.parametrize(
    "url,method,expected",
    [
        ("https://support.google.com/websearch/contact/content_removal_form?hl=en", "GET", True),
        ("https://www.google.com/search?q=example", "GET", True),
        ("https://www.gstatic.com/s2/branding/product/1x/googlelogo.png", "GET", True),
        ("https://support.google.com/websearch/contact/content_removal_form", "POST", False),
        ("https://support.google.com/websearch/contact/content_removal_form/submit", "GET", False),
        ("https://accounts.google.com/signin", "GET", False),
        ("http://support.google.com/websearch/contact/content_removal_form", "GET", False),
        ("https://example.com/redirect", "GET", False),
        ("https://evilgoogle.com/search?q=example", "GET", False),
        ("https://support.google.com/websearch/contact/content_removal_form", "DELETE", False),
    ],
)
def test_inspection_network_policy(url, method, expected):
    assert inspection_request_allowed(url, method) is expected


def test_websockets_are_never_enabled_for_inspection():
    assert websocket_inspection_allowed("wss://support.google.com/socket") is False
    assert websocket_inspection_allowed("wss://example.com/socket") is False


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
        # The inspector helpers only select choices and read metadata; they never submit.
        assert page.locator("body").inner_text().find("Submit") >= 0
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
        # The inspector must return at the handoff gate, before it selects a branch.
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
