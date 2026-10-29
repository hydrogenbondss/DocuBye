# Roadmap

This roadmap is evidence-gated. Do not skip ahead based on a successful demo alone.

## Milestone 0 — Product and safety foundation

**Status: complete**

- [x] Create public repository and MIT licence.
- [x] Define product scope and honest limitations.
- [x] Document architecture and safety guardrails.
- [x] Create an implementation issue for the first vertical slice.

## Milestone 1 — Synthetic browser workflow

**Status: implemented; GitHub Actions browser suite passed**

- [x] Create a local mock opt-out site using synthetic data.
- [x] Add a typed task state machine and a one-time submission-attempt guard.
- [x] Implement Playwright navigation, field mapping, and review preparation.
- [x] Add an explicit approval callback before form submission.
- [x] Add exact-origin request filtering and a pre-approval POST gate for the local fixture.
- [x] Add safe pauses for simulated human verification and unexpected requests.
- [x] Distinguish submitted, awaiting confirmation, and fixture-verified removal.
- [x] Add an optional model-backed field mapper that receives only form metadata and validates its output.
- [x] Add tests for task-state rules, model-output validation, mock-site responses, and loopback URL validation.
- [x] Add a browser test suite and CI workflow that installs Playwright Chromium.
- [x] Verify the full suite in GitHub Actions: 21 tests passed.
- [ ] Review the route guard against redirects, popups, frames, downloads, and other navigation edge cases before real-site work.

**Exit criteria:** CI proves the agent fills the correct fields on the mock site; no submission occurs before approval; a pre-approval POST is blocked; unexpected steps pause safely; and submitted requests are never mislabeled as verified removals. The automated suite passes; the remaining route-boundary review still blocks live-site integration.

## Milestone 2 — First real source

- [ ] Select one source after reviewing its official removal process, terms, required fields, and verification method.
- [ ] Implement a narrowly scoped source adapter rather than letting a model invent arbitrary submission steps.
- [ ] Test navigation and field mapping without submitting a real user's request.
- [ ] Keep a pre-submission review of the destination and data categories.
- [ ] Run a real request only with explicit user authorisation and accurate information supplied by that user.
- [ ] Record the outcome and limitations; never claim deletion without verification.

**Exit criteria:** One real workflow has been exercised end-to-end, failures are handled safely, and submission and removal are reported as different states.

## Milestone 3 — Small reliable queue

- [ ] Queue multiple supported tasks and preserve progress between sessions.
- [ ] Resume paused tasks without resubmitting.
- [ ] Add retry budgets, timeouts, and clear error explanations.
- [ ] Track confirmation emails only with explicit user consent and minimal permissions.
- [ ] Add a way to disable or revoke automation for a source.
- [ ] Publish integration test requirements and a source maintenance checklist.

**Exit criteria:** A small set of integrations is reliable, maintainable, and auditable. Reliability takes priority over integration count.

## Milestone 4 — Discovery and monitoring

- [ ] Add discovery sources incrementally, starting with user-provided URLs and narrowly scoped official/search sources.
- [ ] Add scheduled rechecks where permitted and technically meaningful.
- [ ] Separate removal at the original source from search-result delisting and cached copies.
- [ ] Add jurisdiction-specific workflows only after documenting applicable rules and limitations.

## Non-negotiable release gates

- No unauthorised submissions.
- No CAPTCHA or access-control bypass.
- No secrets in source control or ordinary logs.
- No claim of successful removal without evidence.
- No integration shipped without tests, documented human handoff, and a last-tested date.
