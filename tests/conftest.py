import pytest


@pytest.fixture(scope="session")
def chromium():
    """Browser tests either run against a real Chromium or skip consistently."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
    except Exception as exc:
        pytest.skip(f"Playwright-managed Chromium is unavailable ({exc}); CI installs it")
    return True
