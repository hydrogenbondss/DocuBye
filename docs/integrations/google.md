# Integration: Google Search personal contact-info removal

**Status:** Read-only inspection and dry-run planning implemented. **Submission is intentionally NOT implemented.**  
**Last tested:** 14 November 2026, against sanitized offline fixtures (`tests/fixtures/google/`). The live branch was manually confirmed at the UI-label level on 31 October 2026 (see [FIRST_SOURCE_REVIEW.md](../FIRST_SOURCE_REVIEW.md)); the live site has not been re-driven by this adapter.

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
