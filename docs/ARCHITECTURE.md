# Architecture proposal

**Status:** Initial architecture implemented for the synthetic milestone; review remaining before any live integration.

## Design goal

Make browser automation reliable enough for privacy-sensitive workflows without giving a general-purpose model unlimited authority over the user's browser, data, or identity.

## Current components

### 1. Workflow controller

The agent module owns the permitted workflow. It validates the loopback origin, observes the page, requests a field mapping, prepares a review summary, waits for explicit approval, and records a bounded set of state transitions. The model does not decide whether the submission gate is open.

### 2. Browser driver and network guard

Playwright controls the browser. A context-level route handler permits only requests to the exact mock-site origin, and rejects POSTs to /submit until approval is given. Service workers are blocked for the prototype. The base URL must be plain HTTP on a loopback host and cannot include a path, query, or fragment.

The guard is intended for this local fixture. Do not treat it as a completed production-grade browser sandbox: live-site integrations require a separate security review, more comprehensive navigation controls, and tests around redirects, popups, frames, downloads, browser protocols, and page-initiated network paths.

### 3. Form planner

The planner module defines a protocol, an offline deterministic mapping, and an optional OpenAI Responses API mapper. The model receives only field metadata (name, label, input type, and required flag), never the profile's name, email, phone, cookies, or credentials. Model output is parsed and validated against an allowlist of input names and canonical profile fields.

AI is deliberately constrained to mapping fields in this milestone. It does not have arbitrary browser tools, cannot choose a destination, and cannot approve a submission. A future AI-navigation layer must remain behind an independently enforced navigation boundary.

### 4. Synthetic mock site

The mock-site module serves a local test fixture with the form, a human-verification pause, an unexpected-request pause, and a separate verification endpoint. The special early-submit scenario attempts a POST before review to test the route guard. Test-only form values remain in volatile fixture memory and are not written to logs or disk.

### 5. Task state and evidence

The models module implements a typed state machine and a one-time submission-attempt guard. Public task records contain timestamps, generic action descriptions, status, and a task ID—not profile values or full page content. The verified-removed state is only reached when the fixture's separate verification endpoint confirms removal.

## Proposed tools

- Python 3.11+
- Playwright for browser control and end-to-end testing
- pytest for workflow and safety tests
- SQLite later, once task records need persistence; current task state is in memory
- Optional OpenAI SDK for model-assisted field mapping

## Why not delegate the browser boundary to an AI-agent library yet?

The first prototype should not rely on a library's allowed-domains option as the sole security barrier. Browser-agent domain-restriction bypass concerns have been reported, including a recent report in the Browser Use project: https://github.com/browser-use/browser-use/issues/5815. This is not a conclusion that the library can never be used; DocuBye should independently prove and enforce its network boundary before handing browser control to a more general agent. Reconsider after the synthetic tests and a targeted security review.

## Critical safety controls

- Explicit task scope and user authorisation.
- Approval gate before submission.
- Stop on CAPTCHA, identity verification, login challenge, payment, legal attestation, unclear consent, or unexpected data requests.
- Treat webpage content as untrusted; resist prompt injection.
- Never extract or expose passwords, cookies, authentication tokens, or unrelated page data to the model.
- Redact logs and screenshots; allow users to delete local task history.
- Prevent duplicate submission after a timeout or resume.
- Do not evade a website's security controls or claim an unverified removal.

## Before connecting to a real source

1. Verify the CI browser suite is green with Playwright-managed Chromium.
2. Add security tests for redirects, popup tabs, frames, browser protocols, and attempts to alter the request destination.
3. Pick one official removal workflow and document its required fields, terms, verification method, and human checkpoints.
4. Add a source-specific adapter and avoid arbitrary model-generated clicks for submission.
5. Keep pre-submission review and explicit approval enabled until the integration has adequate safety evidence.
