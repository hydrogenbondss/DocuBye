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

## Licence

MIT. See LICENSE.
