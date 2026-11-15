# Integration: Google Search personal contact-info removal

**Status:** Read-only inspection and dry-run planning implemented. **Submission is intentionally NOT implemented.**  
**Last tested:** 15 November 2026 — offline fixtures green; live run #2 attempted (guard correct; sign-in stonewalled on the automation-flagged Chrome for Testing binary; fix: owner's real Chrome via persistent context). The live branch was manually confirmed at the UI-label level on 31 October 2026 (see [FIRST_SOURCE_REVIEW.md](../FIRST_SOURCE_REVIEW.md)); the live site has not been successfully re-driven by this adapter yet.

## Headed handoff repair (14 November 2026)

**Root cause of the TargetClosedError:** the inspector's popup guard closed every page emitted by the browser context's `page` event. That event fires for the main page itself and for the replacement tab Google's redirect chain can deliver the wizard in, so the guard destroyed the page holding the content; the next locator call on the dead reference raised `TargetClosedError`. **Fix:** the guard now tracks a designated main page and never closes it, and after navigation and after the human handoff the inspector resolves the working page — adopting a single surviving guarded tab, or recording a clean note if the window is gone. Offline regression tests simulate popups, replacement tabs, and window closure.

## Live read-only validation harness

`docubye-capture-google-fixtures` runs a headed, human-driven capture: the owner signs in themselves (the agent never touches credentials), the agent performs only the read-only navigation, and each step's HTML is sanitized (emails, phone numbers, names, avatars, URL/session tokens, account labels) with the redaction diff shown before anything is saved. Captures land in `captures/` (gitignored). Each run ends with a machine-readable selector validation report (found / missing / ambiguous per step, no page content).

- Requires `DOCUBYE_REAL_SOURCE=1` and a typed account confirmation; refuses otherwise.

### Live run, 14 November 2026 — failed closed, as designed

The first live capture run stopped safely: the route guard's live-mode allowlist permitted only the wizard domain, so `accounts.google.com` was blocked and human sign-in was impossible. Zero files saved, zero selector checks, no submission, redacted notes only.

### Live run #2, 15 November 2026 — guard correct; sign-in stonewalled on the automation binary

With the two-phase guard, **no `accounts.google.com` request was blocked** — the guard blocked only telemetry and widget endpoints (`google-analytics`, `googletagmanager`, `play.google.com/log`, `ogads`/`ogs` widgets, and `support.google.com` `/apis/cuf*` and `/s/infolog` — see the note below). Yet sign-in hung indefinitely after email entry. This is the signature of Google stonewalling automation-flagged binaries (Chrome for Testing). The guard behaved correctly; the browser binary was the problem.

**Fix:** the live path now launches the owner's real installed Google Chrome (`channel="chrome"`) via a persistent profile under the gitignored `captures/` directory. There are deliberately **no anti-detection measures** — no `navigator.webdriver` tampering, no user-agent spoofing, no fingerprint tricks. The human performs all authentication in a normal browser binary; DocuBye does not disguise automation from Google. Tests and fixtures keep the Playwright-managed Chromium.

**Allowlist unchanged.** Every host blocked in run #2 was telemetry or widgets. Note: `support.google.com` `/apis/cuf*` and `/s/infolog` were observed blocked while the wizard never loaded. Only if the wizard fails to render *after* a successful sign-in may these be evaluated — one by one, each with written justification — and never implicitly.

### Two-phase guard (15 November 2026)

The guard now has two phases, because the "no POST" invariant applies to agent-driven traffic, not to the human's own authentication:

1. **Sign-in phase** — GET/POST/HEAD to `accounts.google.com` (the human's sign-in form; every interaction is human-driven, the agent sends nothing). GET/HEAD only to the wizard host and static asset hosts.
2. **Wizard phase** — after the wizard domain is verified as loaded, the guard re-locks to GET/HEAD only on the wizard and static hosts; `accounts.google.com` itself becomes unreachable.

If the redirect chain involves any other host, the run stops with a redacted note; the allowlist is never widened implicitly.

| Host | Phases | Methods | Why |
|---|---|---|---|
| `accounts.google.com` | sign-in only | GET/POST/HEAD | Human-driven sign-in form; POSTs are the person's own authentication |
| `support.google.com` | both | GET/HEAD | The removal wizard |
| `www.gstatic.com`, `ssl.gstatic.com`, `fonts.gstatic.com`, `fonts.googleapis.com` | both | GET/HEAD | Static scripts/styles/fonts needed to render Google's pages |
| `google.com`, `www.google.com` | both | GET/HEAD | Wizard-referenced assets |
| Telemetry (`play.google.com`, `google-analytics.com`, `googletagmanager.com`, `ogs.google.com`, …) | neither | none | Not in any allowlist; blocked in both phases |

The handoff gate now requires an empty Enter (non-empty input re-prompts — a pasted shell command previously proceeded) and verifies the wizard domain is actually loaded before capturing; otherwise it pauses with a redacted note instead of producing an empty report.

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
