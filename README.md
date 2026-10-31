# DocuBye

**An open-source AI agent for removing your own digital footprint.**

DocuBye aims to do more than list privacy risks or generate opt-out instructions. It is being designed to carry out authorised removal workflows in a real browser, handle routine steps automatically, ask for help when a site requires human judgement, and keep an honest record of what happened.

> **Project status: early prototype.** The current runnable workflow uses a local synthetic site only. It does not yet connect to real data brokers or submit real removal requests.

## Current prototype

- Local mock opt-out site with synthetic data.
- Playwright-controlled navigation and field filling.
- Optional OpenAI-backed field mapping that receives only form metadata, not profile values.
- Explicit request review and approval before synthetic submission.
- Guards for the exact local origin, expected endpoints, reviewed form payload, and one-time approval.
- Blocks external HTTP paths and WebSockets during the synthetic workflow.
- Human handoff for verification challenges and unexpected requests.
- A state machine that distinguishes submission from a separately verified result.
- A read-only Google form inspector with a headed, operator-assisted observation mode.
- 79 passing tests in the latest green GitHub Actions push and pull-request runs (26.59 seconds on commit `f47b17b`).

## Quick start

Requires Python 3.11+ and Chromium supported by Playwright.

    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -e '.[dev]'
    python -m playwright install chromium
    pytest -q

Run the local demo:

    docubye --scenario normal

The CLI displays the destination and data categories, then asks you to explicitly approve the synthetic submission. Try the safe-pause scenarios:

    docubye --scenario challenge
    docubye --scenario unexpected
    docubye --scenario early-submit
    docubye --scenario verified

The early-submit scenario intentionally attempts a POST before approval. The browser request guard should block it. The verified scenario is a simulated fixture response, not evidence about a real website.

## Optional AI field mapping

The default rules planner is offline and deterministic. To exercise optional model-assisted form-field mapping, install the extra and configure a provider explicitly:

    python -m pip install -e '.[ai]'
    export DOCUBYE_OPENAI_API_KEY='your-key'
    export DOCUBYE_OPENAI_MODEL='your-chosen-model'
    docubye --planner openai --scenario normal

The model receives only input names, field labels, types, and required flags. The profile's name, email, phone number, browser cookies, and credentials are not included in the model request. Remote inference is still a network call, so users should choose their provider deliberately.

## Inspect the first real-source candidate safely

The default command uses a fresh, unauthenticated browser context:

    docubye-inspect-google-form

It prints visible field labels and non-sensitive attributes. It does not fill the form or submit a request. It blocks every non-GET/HEAD request, unapproved hosts, and WebSockets. If a CAPTCHA or human-verification element is visible, automatic mode stops before selecting any branch.

For a person to inspect the live wizard, run the explicit headed handoff:

    docubye-inspect-google-form --headed --human-handoff

The browser remains visible while the terminal waits. A person may inspect the public wizard and select navigation choices, then press Enter to capture visible labels and field metadata. The report includes selected radio labels and blocked-request method/host/path metadata. It strips query strings and fragments from the final URL.

**The human handoff does not relax the network guard.** Only HTTPS GET/HEAD requests to the small Google-host allowlist are permitted. Every POST/PUT/PATCH/DELETE request, unapproved host, WebSocket, and known submission endpoint remains blocked. This may prevent a CAPTCHA or Next button from working. Do not sign in, enter personal information, upload files, click Submit, use an authenticated browser profile, or try to bypass a blocked request. If the branch cannot be reached under these restrictions, stop and record that it remains unverified.

The inspector never reads input values, cookies, request bodies, or screenshots. Its report sets submission and field-filling flags to false. It is a diagnostic for human observation, not a live removal adapter.

The first live inspection found a CAPTCHA before the Next step, so the contact-info sub-branch remains unverified until a person can inspect it through the guarded handoff without bypassing verification or submitting a request.

## First real-source candidate

The Google Search personal contact-info workflow is being investigated, not automated yet. Its current request contract and limitations are documented in docs/FIRST_SOURCE_REVIEW.md. Google Search removal does not delete the original website's content. The live form branch must be interactively inspected without personal data or submission before a browser adapter can be enabled.

## Principles

- Work only on the user's own information or information they are authorised to manage.
- Keep browser sessions and task records local by default.
- Disclose remote model data flow.
- Never bypass CAPTCHAs, access controls, identity checks, or a site's human-verification steps.
- Keep personal fields out of ordinary logs, screenshots, and test reports.
- Never label a request removed just because it was submitted.

## Documentation

- Product brief: docs/PRODUCT_BRIEF.md
- Architecture proposal: docs/ARCHITECTURE.md
- Roadmap: docs/ROADMAP.md
- First-source review: docs/FIRST_SOURCE_REVIEW.md

## Licence

MIT. See LICENSE.
