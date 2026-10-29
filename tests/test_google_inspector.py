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
