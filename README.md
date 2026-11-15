# DocuBye

[![tests](https://github.com/hydrogenbondss/DocuBye/actions/workflows/tests.yml/badge.svg)](https://github.com/hydrogenbondss/DocuBye/actions/workflows/tests.yml)

**An open-source AI agent for removing your own digital footprint.**

DocuBye aims to do more than list privacy risks or generate opt-out instructions. It is being designed to carry out authorised removal workflows in a real browser, handle routine steps automatically, ask for help when a site requires human judgement, and keep an honest record of what happened.

> **Project status: early prototype.** The current runnable workflow uses a local synthetic site only. It does not connect to real data brokers and does not submit real removal requests.

## Current prototype

- Local mock opt-out site with synthetic data loaded from a fixture file.
- Playwright-controlled navigation and deterministic, offline field mapping.
- Explicit request review and approval before synthetic submission.
- Guards for the exact local origin, expected endpoints, reviewed form payload, and one-time approval.
- Blocks external HTTP paths and WebSockets during the synthetic workflow.
- Human handoff for verification challenges and unexpected requests.
- A state machine that distinguishes submission from a separately verified result.
- SQLite task persistence: task ID, full status history, approval state, submission (idempotency) key, and confirmation ID.
- Recovery of interrupted submissions via a read-only status lookup by idempotency key. Automatic blind retry is disabled; approvals stay single-use across process restarts.

## Quick start

Requires Python 3.11+ and Chromium supported by Playwright.

    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -e '.[dev]'
    python -m playwright install chromium
    pytest -q

Run the local demo:

    docubye run --scenario normal

The CLI displays the destination and data categories, then asks you to explicitly approve the synthetic submission. Try the safe-pause scenarios:

    docubye run --scenario challenge
    docubye run --scenario unexpected
    docubye run --scenario early-submit
    docubye run --scenario verified

The early-submit scenario intentionally attempts a POST before approval. The browser request guard should block it. The verified scenario is a simulated fixture response, not evidence about a real website.

## Interrupted-submission recovery demo

The timeout-after-submit scenario records the POST but withholds the acknowledgement marker, so the run ends in the UNKNOWN state:

    docubye run --scenario timeout-after-submit

The CLI prints a recovery command with the task ID. Run it to perform a read-only status lookup by the persisted idempotency key:

    docubye recover <task-id>

Recovery finds the original submission, records its confirmation ID, and moves the task to awaiting_confirmation without sending a second request. Nothing ever resubmits automatically.

## Resuming a paused task

When the workflow pauses (awaiting_user), for example at a simulated verification challenge, a person must resolve the blocking step first. Resuming then continues the same task under the same task ID:

    docubye resume <task-id> --note "Operator cleared the simulated check" --confirm-human-resolution

The note is redacted and recorded in the task history. The resumed task is re-inspected and freshly reviewed; it can never resume into submission, and rejection is terminal — a rejected task requires a fresh task.
## First real-source candidate (research only)

The Google Search personal contact-info workflow is being investigated, not automated. This branch adds a read-only inspector and a request contract; there is no live browser adapter and no submission path. The full findings and limitations are in docs/FIRST_SOURCE_REVIEW.md. Google Search removal does not delete the original website's content.

The default command uses a fresh, unauthenticated browser context:

    docubye-inspect-google-form

It prints visible field labels and non-sensitive attributes. It does not fill the form or submit a request. It blocks every non-GET/HEAD request, unapproved hosts, and WebSockets. If a CAPTCHA or human-verification element is visible, automatic mode stops before selecting any branch.

For a person to inspect the live wizard, run the explicit headed handoff:

    docubye-inspect-google-form --headed --human-handoff

The browser remains visible while the terminal waits. A person may inspect the public wizard and select navigation choices, then press Enter to capture visible labels and field metadata. **The human handoff does not relax the network guard.** Only HTTPS GET/HEAD requests to the small Google-host allowlist are permitted. Every POST/PUT/PATCH/DELETE request, unapproved host, WebSocket, and known submission endpoint remains blocked. This may prevent a CAPTCHA or Next button from working. Do not sign in, enter personal information, upload files, click Submit, use an authenticated browser profile, or try to bypass a blocked request. If the branch cannot be reached under these restrictions, stop and record that it remains unverified.

The inspector never reads input values, cookies, request bodies, or screenshots. Its report sets submission and field-filling flags to false. It is a diagnostic for human observation, not a live removal adapter.

A manual inspection in the user's regular browser on 31 October 2026 confirmed that selecting “Content contains your personal information” reaches the live contact-info form state. The visible prompts include the address/phone/email value as it appears on the page, a separate email field as it appears on the page, and a required question about malicious or threatening intent. No values were entered and nothing was submitted. The exact selector choices, doxxing answer choices, lower-page fields, stable DOM selectors, and required flags are still being recorded. The headed Playwright handoff separately failed to render a usable page (`TargetClosedError`), so this manual observation does not mean the automated inspector or a live adapter is complete. The contact-info branch has been manually confirmed at the UI-label level only; no live adapter or submission capability is enabled.

### Read-only dry-run adapter (Milestone 2, session 1)

**Read-only inspection implemented; submission intentionally not yet implemented.** The adapter navigates the documented flow, pauses at sign-in walls and CAPTCHAs, collects field metadata, and produces a dry-run plan — then stops. No code path fills a field, clicks Submit, or sends a request body.

    docubye-google-dry-run                      # offline fixtures (default, CI-safe)
    docubye-google-dry-run --scenario captcha   # pause-path scenarios
    DOCUBYE_REAL_SOURCE=1 docubye-google-dry-run --live   # explicit opt-in, read-only

Details, failure states, and boundaries: docs/integrations/google.md.

The headed handoff lifecycle bug (`TargetClosedError`) is fixed: the popup guard no longer closes the page carrying the wizard, and a surviving guarded tab is adopted when the wizard moves. For owner-run live validation of the read path (headed, real installed Chrome, you sign in yourself, sanitized captures, selector report):

    DOCUBYE_REAL_SOURCE=1 docubye-capture-google-fixtures

Captures are sanitized with the redaction diff shown before saving, land in the gitignored `captures/` directory, and the run prints a machine-readable selector validation report containing no page content.

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
- Stack decision record: docs/STACK_DECISION.md
- Google integration (read-only dry run): docs/integrations/google.md

## Licence

MIT. See LICENSE.
