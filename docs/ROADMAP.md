# Roadmap

This roadmap is evidence-gated. Do not skip ahead based on a successful demo alone.

## Milestone 0 — Product and safety foundation

**Status: complete**

- [x] Create public repository and MIT licence.
- [x] Define product scope and honest limitations.
- [x] Document architecture and safety guardrails.
- [x] Create an implementation issue for the first vertical slice.

## Milestone 1 — Synthetic browser workflow

**Status: implemented; expanded security regression tests in progress**

- [x] Create a local mock opt-out site using synthetic data.
- [x] Add a typed task state machine and a one-time submission-attempt guard.
- [x] Implement Playwright navigation, field mapping, and review preparation.
- [x] Add an explicit approval callback before form submission.
- [x] Limit the synthetic workflow to the exact local origin and a small endpoint/method allowlist.
- [x] Require the single approved submission to be a main-frame document POST with a payload matching the reviewed form.
- [x] Consume the one-time approval before forwarding the submission.
- [x] Add safe pauses for simulated human verification and unexpected requests.
- [x] Distinguish submitted, awaiting confirmation, and fixture-verified removal.
- [x] Add an optional model-backed field mapper that receives only form metadata and validates its output.
- [x] Add a browser test suite for external requests, redirects, popups, frames, altered form actions/payloads, and duplicate submission attempts.
- [ ] Verify the expanded browser suite in GitHub Actions before proceeding to a real-site adapter.
- [ ] Conduct a broader security review for downloads, browser protocols, and remaining navigation edge cases.

**Exit criteria:** CI proves the agent fills the correct fields on the mock site; the browser cannot submit before approval; the one-time gate cannot be reused; altered requests are blocked; unexpected steps pause safely; and submitted requests are never mislabeled as verified removals.

## Milestone 2 — First real source

Candidate selected for investigation: Google's official personal-information removal form for Google Search. This is a search-result delisting workflow, not removal from the underlying website.

- [ ] Document the official flow, supported request categories, required URLs, contact information, jurisdiction caveats, and verification states.
- [ ] Add a source adapter that only targets the verified official Google form domains.
- [ ] Test the adapter without submitting any actual personal information.
- [ ] Keep a pre-submission review of the destination and data categories.
- [ ] Require explicit user authorisation before any real request is submitted.
- [ ] Record only minimal evidence; distinguish request receipt, Google's decision, and actual search-result changes.

**Exit criteria:** One official workflow is exercised with explicit authorisation, failures are handled safely, and the original source is clearly distinguished from Google Search results.

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
