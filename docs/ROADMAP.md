# Roadmap

This roadmap is evidence-gated. Do not skip ahead based on a successful demo alone.

## Milestone 0 — Product and safety foundation

**Status: complete**

- [x] Create public repository and MIT licence.
- [x] Define product scope and honest limitations.
- [x] Document architecture and safety guardrails.
- [x] Create an implementation issue for the first vertical slice.

## Milestone 1 — Synthetic browser workflow

**Status: implemented; CI browser suite passed**

- [x] Create a local mock opt-out site using synthetic data.
- [x] Add a typed task state machine and a one-time submission-attempt guard.
- [x] Implement Playwright navigation, field mapping, and review preparation.
- [x] Add an explicit approval callback before form submission.
- [x] Limit the synthetic workflow to the exact local origin and a small endpoint/method allowlist.
- [x] Require the single approved submission to be a main-frame document POST with a payload matching the reviewed form.
- [x] Consume the one-time approval before forwarding the submission.
- [x] Block outbound HTTP navigation paths and WebSockets in the synthetic browser.
- [x] Add safe pauses for simulated human verification and unexpected requests.
- [x] Distinguish submitted, awaiting confirmation, and fixture-verified removal.
- [x] Add an optional model-backed field mapper that receives only form metadata and validates its output.
- [x] Add browser tests for external requests, redirects, popups, frames, WebSockets, altered form actions/payloads, duplicate submission attempts, and approval states.
- [x] Verify the full suite in GitHub Actions: 28 tests passed.
- [ ] Review the route guard for downloads, browser protocols, and remaining navigation edge cases before a live-site adapter.

**Exit criteria:** CI proves the agent fills the correct fields on the mock site; the browser cannot submit before approval; the one-time gate cannot be reused; altered requests are blocked; unexpected steps pause safely; and submitted requests are never mislabeled as verified removals.

## Milestone 2 — First real source

Candidate: Google's official personal-contact-information Search-removal flow. This is request-contract preparation, not a working browser adapter. See [first-source review](FIRST_SOURCE_REVIEW.md) and [Issue #3](https://github.com/hydrogenbondss/DocuBye/issues/3).

- [x] Inspect official form text without submitting and record the categories/fields visible in the current page source.
- [x] Add a pure request-draft, review, redacted-audit, and one-time-approval contract for address/phone/email.
- [x] Add a read-only local inspector command that selects the contact-info branch and records visible field metadata without filling or submitting.
- [ ] Run the inspector locally and inspect the active contact-info branch without personal data or submission.
- [ ] Confirm exact active fields and stable selectors; pause on uncertainty.
- [ ] Implement a narrowly scoped Playwright adapter for the confirmed official branch.
- [ ] Test navigation, field filling, request approval, and route guard on a local simulated form.
- [ ] Conduct a non-submitting smoke test against the live form without any real profile data.
- [ ] Enable real submissions only after user review and explicit approval, outside automated tests.
- [ ] Record request receipt, Google's decision, and observed Search result changes as separate states.

**Exit criteria:** The live workflow is verified without submission first; any real submission requires exact user approval; the source adapter is narrow and tested; logs redact values; and no result is called removed without verification.

## Milestone 3 — Small reliable queue

- [ ] Queue multiple supported tasks and preserve progress between sessions.
- [ ] Resume paused tasks without resubmitting.
- [ ] Add retry budgets, timeouts, and clear error explanations.
- [ ] Track confirmation emails only with explicit user consent and minimal permissions.
- [ ] Add a way to disable or revoke automation for a source.
- [ ] Publish integration test requirements and a source maintenance checklist.

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
