# Integration: Google Search personal contact-info removal

**Status:** Read-only inspection and dry-run planning implemented. **Submission is intentionally NOT implemented.**  
**Last tested:** 14 November 2026, against sanitized offline fixtures (`tests/fixtures/google/`). The live branch was manually confirmed at the UI-label level on 31 October 2026 (see [FIRST_SOURCE_REVIEW.md](../FIRST_SOURCE_REVIEW.md)); the live site has not been re-driven by this adapter.

## Headed handoff repair (14 November 2026)

**Root cause of the TargetClosedError:** the inspector's popup guard closed every page emitted by the browser context's `page` event. That event fires for the main page itself and for the replacement tab Google's redirect chain can deliver the wizard in, so the guard destroyed the page holding the content; the next locator call on the dead reference raised `TargetClosedError`. **Fix:** the guard now tracks a designated main page and never closes it, and after navigation and after the human handoff the inspector resolves the working page — adopting a single surviving guarded tab, or recording a clean note if the window is gone. Offline regression tests simulate popups, replacement tabs, and window closure.

## Live read-only validation harness

`docubye-capture-google-fixtures` runs a headed, human-driven capture: the owner signs in themselves (the agent never touches credentials), the agent performs only the read-only navigation, and each step's HTML is sanitized (emails, phone numbers, names, avatars, URL/session tokens, account labels) with the redaction diff shown before anything is saved. Captures land in `captures/` (gitignored). Each run ends with a machine-readable selector validation report (found / missing / ambiguous per step, no page content).

- Requires `DOCUBYE_REAL_SOURCE=1` and a typed account confirmation; refuses otherwise.
- **Live run:** pending owner execution. Selector validation result: pending. Fixtures will be updated only from that report; raw captures are never committed.

## What this integration does

`docubye-google-dry-run` (module `src/docubye/sources/google.py`) navigates the documented Google personal-contact-information removal wizard in a real browser, collects visible field metadata (never input values), and produces a **dry-run plan** for human review. It then stops. Task state, history, and the plan are recorded in the local SQLite store.

## Workflow

1. Open `https://support.google.com/websearch/contact/content_removal_form?hl=en` (live mode only with `DOCUBYE_REAL_SOURCE=1`; default and CI use recorded fixtures).
2. Pause to `awaiting_user` if a sign-in wall, CAPTCHA, or identity check is visible. DocuBye does not automate or bypass these.
3. Select "Content contains your personal information", then "Address, phone number, and/or e-mail address". If either control is missing or ambiguous, pause — no guessing.
4. Verify every form destination and submit-control target matches the documented form path; pause on any mutation.
5. Collect visible field metadata (names, labels, types, required flags — never values) and map fields through the deterministic planner.
6. Produce the dry-run plan and transition to `ready_for_review`. Stop.

## Required data for a future real request

The exposed contact value as shown on the page, content URL(s), Google Search results URL(s), search terms, country of residence, and a contact email. Three attestations — accuracy, authority, and the search-delisting scope acknowledgement — are human-only and must never be asserted by the adapter.

## Verification method

Not applicable yet. A submitted request is not proof of removal; Google's decision and observed Search-result changes must be recorded as separate states when submission is eventually implemented.

## Failure states

| Condition | Task state | Behaviour |
|---|---|---|
| Sign-in wall | `awaiting_user` | Pause; credentials are never entered |
| CAPTCHA / identity check | `awaiting_user` | Pause; never bypassed |
| Missing/ambiguous branch control | `awaiting_user` | Pause; no guessing |
| Mutated form destination | `awaiting_user` | Pause; no plan produced |
| Page-initiated POST or external request | `awaiting_user` | Blocked by the route guard; recorded redacted (method/host/path only) |
| Browser failure | `failed` | Safe stop; inspect before retrying |

## Hard boundaries

- No code path fills a field, clicks Submit, or sends a request body. The route guard blocks every POST/PUT/PATCH/DELETE, unapproved host, and WebSocket; the fixture server asserts it received zero POSTs.
- Logging is redacted: no personal values, cookies, credentials, or request bodies in task events or reports.
- Live navigation requires `DOCUBYE_REAL_SOURCE=1`; tests and CI never contact Google.
