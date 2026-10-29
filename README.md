# DocuBye

**An open-source AI agent for removing your own digital footprint.**

DocuBye aims to do more than list privacy risks or generate opt-out instructions. It is being designed to carry out authorised removal workflows in a real browser, handle routine steps automatically, ask for help when a site requires human judgement, and keep an honest record of what happened.

> **Project status: early prototype.** The current implementation is a local synthetic-site workflow. It does not yet connect to real data brokers or accept real personal information. The optional AI planner maps field labels; Playwright controls the browser and enforces the local-only boundary and approval gate.

## Current prototype

- Local mock opt-out site with synthetic data.
- Playwright-controlled navigation and field filling.
- Optional OpenAI-backed field mapping that receives only form metadata, not profile values.
- Request review and explicit approval before submission.
- Route guard blocks non-loopback navigation and any form submission before approval.
- Human handoff for verification challenges, unexpected fields, and out-of-scope requests.
- A state machine that distinguishes a submitted request from a verified removal.
- Test scenarios for an attempted pre-approval submission, a human-verification screen, an unexpected request, and a simulated successful verification.

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

The early-submit scenario intentionally attempts a POST before the user has approved. The browser request guard should block it. The verified scenario is a simulated fixture response, not evidence about a real website.

### Optional AI field mapping

The default rules planner is offline and deterministic. To exercise the optional model-assisted form-field mapping, install the extra and configure a provider explicitly:

    python -m pip install -e '.[ai]'
    export DOCUBYE_OPENAI_API_KEY='your-key'
    export DOCUBYE_OPENAI_MODEL='your-chosen-model'
    docubye --planner openai --scenario normal

The model receives only input names, field labels, types, and required flags. The profile's name, email, phone number, browser cookies, and credentials are not included in the model request. Remote inference is still a network call, so users should choose their provider deliberately.

If DOCUBYE_CHROMIUM_EXECUTABLE is set, the runner uses that local Chromium binary. Otherwise, it uses Playwright's installed browser.

## Principles

- **The user owns the task.** Work only on the user's own information or information they are authorised to manage.
- **Local-first.** Keep browser sessions and task records on the user's machine by default. Clearly disclose any data sent to a remote model or service.
- **Human control without busywork.** The user authorises the scope; the agent handles routine steps within that scope and stops when the action falls outside it.
- **Evidence over promises.** A request being submitted is not proof that information was deleted.
- **No evasion.** Do not bypass CAPTCHAs, access controls, identity checks, or a site's explicit human-verification steps.
- **Minimise sensitive data.** Do not log personal fields, cookies, credentials, or full page contents unnecessarily.

## Documentation

- Product brief: docs/PRODUCT_BRIEF.md
- Architecture proposal: docs/ARCHITECTURE.md
- Roadmap: docs/ROADMAP.md

## What DocuBye cannot promise

No tool can guarantee that every trace of a person will disappear from the internet. Some information cannot be removed, some sources have lawful retention requirements, and copies may persist outside the original site's control. DocuBye should report limitations plainly and never label a request removed without adequate verification.

## Contributing

The project is still an early prototype. Please open an issue before contributing a new integration or proposing a significant architectural change. Every integration should document the supported workflow, required data, verification method, failure states, and the last date it was tested.

## Licence

MIT. See LICENSE.
