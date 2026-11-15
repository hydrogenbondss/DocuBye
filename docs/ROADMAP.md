# Roadmap

This roadmap is deliberately evidence-gated. Do not skip ahead based on a successful demo alone.

## Milestone 0 — Product and safety foundation

**Status:** In progress

- [x] Create public repository and MIT licence.
- [x] Write initial product brief.
- [x] Record the proposed architecture and guardrails.
- [x] Define a simulated-first acceptance test.
- [x] Confirm the first implementation stack and record the decision (see [stack decision record](STACK_DECISION.md)).
- [ ] Add contribution, reporting, and security guidance before inviting outside contributors.

**Exit criteria:** Scope, permissions, data handling, and the first workflow are clear enough to implement without inventing product policy during coding.

## Milestone 1 — Synthetic browser workflow

**Status:** Ready for review — synthetic scope only. CI evidence is in the [Actions tab](https://github.com/hydrogenbondss/DocuBye/actions/workflows/tests.yml); nothing here demonstrates real-source removal.

- [x] Create a local mock site that represents a typical opt-out form.
- [x] Create a synthetic profile and a fixture with no real personal information.
- [x] Navigate to the form and map the approved fields.
- [x] Show the request destination and data summary.
- [x] Block submission until approval is explicitly given.
- [x] Capture minimal task evidence and implement clear state transitions.
- [x] Add tests for incorrect mappings, prompt injection, timeout, retry, and duplicate-submission prevention.
- [x] Demonstrate a human handoff for a simulated CAPTCHA or identity check.

_Amendment (PR #2 review): recovery and persistence requirements added explicitly, not substituted for the originals._

- [x] Persist task state (task ID, approval state, submission key, and confirmation ID) in SQLite.
- [x] Recover an interrupted (UNKNOWN) submission only via a read-only status lookup by idempotency key; automatic blind retry stays disabled.
- [x] Keep approvals single-use across process restarts.

**Exit criteria:** Repeatable automated tests prove the permission gates and state machine work. Screenshots or logs do not leak personal values.

## Milestone 2 — First real source

- [ ] Review the route guard for downloads, browser protocols, and remaining navigation edge cases (prerequisite for any live adapter; moved here from Milestone 1).
- [ ] Select one source after reviewing the official removal process, terms, required fields, and verification method.
- [ ] Implement a narrowly scoped source adapter.
- [ ] Test on the official workflow without submitting a real user's request.
- [ ] Add a pre-submission review of the destination and data categories.
- [ ] Run one real request only with the user's explicit authorisation and the required accurate information.
- [ ] Record the actual outcome and limitations; don't claim deletion without verification.

_Amendment (first-source research branch): candidate selected — Google's official personal-contact-information Search-removal flow. Research progress below is request-contract preparation and read-only inspection, not a working adapter. See [first-source review](FIRST_SOURCE_REVIEW.md)._

- [x] Inspect official form text without submitting and record the categories/fields visible in the current page source.
- [x] Add a pure request-draft, review, redacted-audit, and one-time-approval contract for address/phone/email.
- [x] Add a read-only inspector that records visible field metadata and stops before branch selection whenever a CAPTCHA/human-verification element is visible.
- [x] Add a headed operator-handoff mode: manual observation only, no input filling/value reads, and the exact GET/HEAD host guard remains enforced.
- [x] Manually confirm in the user's regular browser that selecting “Content contains your personal information” reaches the live contact-info form state and exposes the required address/phone/email value prompt (31 October 2026; no values entered and nothing submitted).
- [ ] Capture the exact choices for the personal-information selector and doxxing question, plus all lower-page fields and declarations.
- [ ] Diagnose the headed Playwright handoff failure (`TargetClosedError` / no usable page) and obtain safe field metadata without weakening the no-submission boundary.
- [ ] Confirm stable active-field selectors/attributes and all required flags; pause on uncertainty.
- [ ] Implement a narrowly scoped Playwright adapter for the confirmed official branch.
- [ ] Test navigation, field filling, request approval, and route guard on a local simulated form.
- [ ] Conduct a non-submitting smoke test against the live form without any real profile data.
- [ ] Enable real submissions only after user review and explicit approval, outside automated tests.
- [ ] Record request receipt, Google's decision, and observed Search result changes as separate states.

**Exit criteria:** At least one real workflow has been exercised end-to-end, failures are handled safely, and submission and removal are reported as different states.

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

**Exit criteria:** Every finding has a source, confidence level, recommended action, and clear verification status.

## Later — Broader ecosystem

Possible future work includes additional countries, community-maintained adapters, local-model support, and integrations for account deletion or search-result removal. These should follow evidence of a reliable core, not precede it.

## Non-negotiable release gates

- No unauthorised submissions.
- No CAPTCHA or access-control bypass.
- No secrets in source control or ordinary logs.
- No claim of successful removal without evidence.
- No integration shipped without tests, a documented human-handoff path, and a last-tested date.
