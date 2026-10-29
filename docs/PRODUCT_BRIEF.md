# Product brief

**Status:** Draft — product direction for the first implementation  
**Working name:** DocuGone  
**Product category:** Open-source, local-first AI privacy-removal agent

## 1. Problem

People can spend hours discovering where personal information is exposed, locating each site's opt-out process, completing inconsistent forms, handling follow-up emails, and checking whether anything changed. Existing directories and request generators help, but many workflows still leave the person to do the repetitive browser work.

DocuGone's differentiator should be execution, not merely advice: it should operate a real browser to complete authorised, supported removal workflows and show exactly what happened.

## 2. Target user

A person who wants to reduce exposure of their own personal information online and is willing to configure a privacy profile, authorise a clearly scoped cleanup task, and intervene when a site requires human action.

The product must not be built as a people-search or surveillance system. It is for the user’s own information or information they are authorised to manage.

## 3. Product promise

**Tell DocuGone what information you want to remove. It handles supported routine steps, asks only when necessary, and shows verifiable outcomes.**

This is an aspiration, not a claim that the current repository already does it. The product cannot promise universal or permanent deletion.

## 4. Proposed user journey

1. The user selects or enters a supported source or an exposed-information URL.
2. DocuGone explains what information it has identified, the intended destination, and the next action.
3. The user chooses the scope and authorises the task.
4. The agent navigates the source's official process, maps known fields, and fills the form.
5. Before the first external submission in the MVP, DocuGone presents a review showing the destination and the exact categories of data to be sent.
6. After approval, the agent submits only the authorised request and captures a minimal evidence record.
7. If it encounters an unanticipated declaration, CAPTCHA, identity check, login challenge, payment, unclear consent, or other out-of-scope step, it pauses and requests human help.
8. DocuGone tracks confirmation and verifies removal where the source provides a meaningful way to do so.

## 5. MVP scope

The first release should be a narrow vertical slice, not a general-purpose autonomous web crawler.

### Include

- A controlled, synthetic test website with a mock opt-out form.
- A browser agent that can inspect a page, identify form fields, and execute a bounded workflow.
- A typed task state machine and a minimal local record of progress.
- A review/approval gate before an external request can be submitted.
- A human handoff for verification or steps outside the authorised scope.
- Evidence capture that avoids storing unnecessary personal data.
- Automated tests for field mapping, approval gates, failure states, retries, and status reporting.
- After the simulated path is reliable, one carefully selected real source with an official removal procedure.

### Explicitly out of scope for the first release

- Claiming to find every mention of a person on the internet.
- Broad web crawling or automated collection of other people's personal information.
- Automatically submitting to hundreds of sites before integrations are tested.
- Bypassing CAPTCHA, login, identity-verification, rate limits, or access controls.
- Making legal eligibility determinations on the user's behalf.
- Claiming a request succeeded merely because a form was submitted.
- Storing raw credentials, cookies, identity documents, or full page snapshots in ordinary logs.

## 6. Product principles

### Execution with bounded authority

The user should not have to click every routine field. They should authorise a defined cleanup task, and the agent should work within that scope. The MVP still requires an explicit review before an external request is sent. Later, users may be able to pre-authorise clearly defined low-risk actions in a policy they can inspect and revoke.

### Privacy minimisation

Keep data on the user's device by default. Send only the minimum page context and personal fields needed to the chosen model provider, and disclose when remote inference is enabled. Do not assume that a local browser means a cloud LLM never sees its inputs.

### Treat websites as untrusted input

Page text may contain misleading instructions or prompt-injection attempts. Website content may inform what a form asks for, but it must not be allowed to change DocuGone's permissions, reveal secrets, widen the task scope, or override the user's authorisation.

### Report states honestly

Use explicit statuses such as: discovered, ready_for_review, awaiting_user, submitted, awaiting_confirmation, verified_removed, rejected, failed, and unknown. Only use verified_removed when the verification evidence supports it.

## 7. First milestone acceptance criteria

The simulated workflow is complete when:

- A synthetic user profile can be loaded without using real personal data.
- The agent reaches the test site and maps the intended fields correctly.
- It does not submit until the approval gate is explicitly satisfied.
- It refuses an unexpected or out-of-scope action and offers a clear human handoff.
- The task record distinguishes submission from confirmation and verified removal.
- Logs and test artifacts do not expose synthetic fields in places where sensitive values would be written in production.
- Automated tests cover success, rejection, timeout, duplicate submission prevention, and recovery after a paused state.

## 8. Initial success measures

Measure the workflow, not the volume of claimed removals:

- Percentage of supported test tasks completed without manual browser interaction, excluding required approvals and identity checks.
- Correct field-mapping and request-destination rate.
- Duplicate or unauthorised submission count (target: zero).
- Percentage of outcomes supported by evidence.
- Amount of personal data persisted or sent to a model.
- Recovery rate for interrupted tasks without accidentally submitting twice.

## 9. Naming

DocuGone is the current working name, not a claim of trademark clearance. Revisit domain and trademark availability before investing in launch branding. The product identity should focus on digital-footprint removal, not document signing or file deletion.
