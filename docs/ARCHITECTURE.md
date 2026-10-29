# Architecture proposal

**Status:** Proposed starting point. Validate with a small proof of concept before locking major dependencies.

## Design goal

Make browser automation reliable enough for privacy-sensitive workflows without giving a general-purpose model unlimited authority over the user's browser, data, or identity.

## Proposed components

### 1. User interface

Start with a local application that lets the user define a task, inspect the intended request, approve it, follow the agent's progress, and take over when required. A polished multi-account cloud service is not part of the MVP.

### 2. Task orchestrator

A small, explicit state machine should own the workflow. It decides which actions are permitted, tracks state, prevents duplicate submissions, and provides a resumable pause for human intervention. The language model proposes or performs bounded actions; it does not own the permission model.

### 3. Browser driver

Use Playwright for controlled browser interaction, test fixtures, deterministic locators, screenshots, and assertions. Evaluate the open-source Browser Use agent library as an optional navigation layer for unfamiliar or variable pages. Keep the browser-agent interface replaceable so the product is not locked to one model or hosted browser service.

Recommended approach: deterministic site-specific steps wherever the workflow is known; AI-guided exploration only where variation makes fixed steps insufficient. Don't ask an LLM to rediscover a stable form from scratch on every run.

### 4. Source adapter registry

Each supported source should declare, in version-controlled code or data:

- Source name and official domain(s).
- Official removal workflow and documentation URLs.
- Information fields required and why they are required.
- Supported jurisdictions or eligibility caveats, if known.
- Steps the agent may perform.
- Mandatory human checkpoints.
- Confirmation and verification method.
- Retry and duplicate-submission policy.
- Known limitations, last-tested date, and integration tests.

Adapters must be narrowly scoped. The agent must not follow a redirect to an unrelated domain and continue sending personal data without reassessing the destination.

### 5. Local state and evidence

Use SQLite for task metadata in the MVP. Avoid persisting raw personal fields by default. Store secrets in the operating system's secure credential store if persistence is later needed. Evidence should be minimal and redacted: timestamps, source, action taken, status, and a confirmation reference where appropriate—not full page dumps or session cookies.

SQLite by itself is not encryption. Do not describe the database as encrypted unless an encryption layer is implemented and tested.

### 6. Model provider interface

Keep the model provider configurable. Local inference can improve privacy but may reduce capability or require substantial hardware. Hosted models can improve task performance but may receive page text and the minimum personal information included in prompts. Make this data flow visible and configurable; do not silently send all page content or the full identity profile.

### 7. Tests and development tooling

Initial recommendation:

- Python 3.12+ for the orchestrator and Browser Use evaluation.
- Playwright for browser control and end-to-end test coverage.
- Pydantic-style schemas (or equivalent typed models) for task data and adapter contracts.
- SQLite for local task metadata.
- pytest for state machine, adapter, and browser workflow tests.
- uv for Python dependency and environment management.
- A local mock opt-out site with synthetic data for all initial end-to-end tests.

Confirm the exact tool versions and package APIs at implementation time. Avoid adding a frontend framework, cloud database, queue service, or container orchestration before a working vertical slice needs it.

## Critical safety controls

- Explicit task scope and user authorisation.
- Approval gate before external submission in the MVP.
- Stop on CAPTCHA, identity verification, login challenge, payment, legal attestation, unclear consent, or unexpected data requests.
- Treat webpage content as untrusted; resist prompt injection.
- Never extract or expose passwords, cookies, authentication tokens, or unrelated page data to the model.
- Redact logs and screenshots; allow users to delete local task history.
- Prevent duplicate submission after a timeout or resume.
- Do not evade a website's security controls or claim an unverified removal.

## Architecture decision to validate first

Run one synthetic workflow through Playwright, then compare adding Browser Use for the uncertain navigation step. Choose the smallest configuration that is sufficiently robust, observable, and privacy-preserving. Do not adopt hosted browser infrastructure for the initial proof of concept.
