# Roadmap

This roadmap is deliberately evidence-gated. Do not skip ahead based on a successful demo alone.

## Milestone 0 — Product and safety foundation

**Status:** In progress

- [x] Create public repository and MIT licence.
- [x] Write initial product brief.
- [x] Record the proposed architecture and guardrails.
- [x] Define a simulated-first acceptance test.
- [ ] Confirm the first implementation stack and record the decision.
- [ ] Add contribution, reporting, and security guidance before inviting outside contributors.

**Exit criteria:** Scope, permissions, data handling, and the first workflow are clear enough to implement without inventing product policy during coding.

## Milestone 1 — Synthetic browser workflow

- [ ] Create a local mock site that represents a typical opt-out form.
- [ ] Create a synthetic profile and a fixture with no real personal information.
- [ ] Navigate to the form and map the approved fields.
- [ ] Show the request destination and data summary.
- [ ] Block submission until approval is explicitly given.
- [ ] Capture minimal task evidence and implement clear state transitions.
- [ ] Add tests for incorrect mappings, prompt injection, timeout, retry, and duplicate-submission prevention.
- [ ] Demonstrate a human handoff for a simulated CAPTCHA or identity check.

**Exit criteria:** Repeatable automated tests prove the permission gates and state machine work. Screenshots or logs do not leak personal values.

## Milestone 2 — First real source

- [ ] Select one source after reviewing the official removal process, terms, required fields, and verification method.
- [ ] Implement a narrowly scoped source adapter.
- [ ] Test on the official workflow without submitting a real user's request.
- [ ] Add a pre-submission review of the destination and data categories.
- [ ] Run one real request only with the user's explicit authorisation and the required accurate information.
- [ ] Record the actual outcome and limitations; don't claim deletion without verification.

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
- [ ] Add jurisdiction-specific workflows only after documenting the applicable rules and limitations.

**Exit criteria:** Every finding has a source, confidence level, recommended action, and clear verification status.

## Later — Broader ecosystem

Possible future work includes additional countries, community-maintained adapters, local-model support, and integrations for account deletion or search-result removal. These should follow evidence of a reliable core, not precede it.

## Non-negotiable release gates

- No unauthorised submissions.
- No CAPTCHA or access-control bypass.
- No secrets in source control or ordinary logs.
- No claim of successful removal without evidence.
- No integration shipped without tests, a documented human-handoff path, and a last-tested date.
