# Integration: Google Search personal contact-info removal

**Status:** Read-only inspection and dry-run planning implemented. **Submission is intentionally NOT implemented.**  
**Last tested:** 15 November 2026 — offline fixtures green; automated live capture attempted (runs of 14–15 Nov) and abandoned: Google stonewalls automation-controlled browsers at sign-in, and DocuBye does not evade that. The supported validation path is manual capture (below). The live branch was manually confirmed at the UI-label level on 31 October 2026 (see [FIRST_SOURCE_REVIEW.md](../FIRST_SOURCE_REVIEW.md)).

## Headed handoff repair (14 November 2026)

**Root cause of the TargetClosedError:** the inspector's popup guard closed every page emitted by the browser context's `page` event. That event fires for the main page itself and for the replacement tab Google's redirect chain can deliver the wizard in, so the guard destroyed the page holding the content; the next locator call on the dead reference raised `TargetClosedError`. **Fix:** the guard now tracks a designated main page and never closes it, and after navigation and after the human handoff the inspector resolves the working page — adopting a single surviving guarded tab, or recording a clean note if the window is gone. Offline regression tests simulate popups, replacement tabs, and window closure.

## Live read-only validation harness (deprecated)

`docubye-capture-google-fixtures` was a headed, human-driven capture tool. **Its live path is deprecated** (see the runs below); its fixture path remains in use for offline tests. Do not run it against the live site.

### Live runs, 14–15 November 2026 — automated capture attempted and abandoned

Run #1 (14 Nov) failed closed: the live allowlist blocked `accounts.google.com`, so sign-in was impossible; zero data captured. Run #2 (15 Nov), with the two-phase guard: the guard blocked only telemetry/widgets and no auth traffic, yet sign-in hung indefinitely after email entry — the signature of Google stonewalling automation-controlled browser binaries (Chrome for Testing), including a real-Chrome persistent profile under automation control.

**Decision:** automated live capture is abandoned. DocuBye's no-evasion principles mean we will not fight Google's automation detection. No browser automation approaches sign-in, ever. The `docubye-capture-google-fixtures` live path is **deprecated**; its fixture path remains in use for offline tests.

**The supported validation path is manual capture** (below): the owner does everything in their own everyday browser, and the tooling only reads locally saved HTML files.

**Allowlist unchanged.** Every host blocked in run #2 was telemetry or widgets. Note: `support.google.com` `/apis/cuf*` and `/s/infolog` were observed blocked while the wizard never loaded. Only if the wizard fails to render *after* a successful sign-in may these be evaluated — one by one, each with written justification — and never implicitly.

### Two-phase guard (15 November 2026)

The guard now has two phases, because the "no POST" invariant applies to agent-driven traffic, not to the human's own authentication. It remains in force for the (deprecated) live path and the fixture-based tests:

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

## Manual capture (supported path)

No browser automation is involved. You do everything in your own everyday browser; the tooling only reads files you saved locally.

1. In your own browser, sign in to Google as yourself and open the removal form: https://support.google.com/websearch/contact/content_removal_form?hl=en
2. Walk the wizard steps manually, one step at a time. At each step, save the page: **File → Save As → "Webpage, HTML Only"** into a new local folder, naming files in order: `01-start.html`, `02-personal-info.html`, `03-contact-branch.html`, and so on.
3. Run the offline report tool on that folder:

   `docubye-google-report --html-dir <your-folder>`

4. For each file the tool prints a redaction summary (counts and types of removed items, never the values), asks whether to keep a sanitized copy (opt-in, saved to the gitignored `captures/` directory), and runs the selector validation offline.
5. The tool prints a machine-readable JSON report: per-step selector found/missing/ambiguous, processed file names, and blocked asset-request count. It contains no page content and no personal values. Share only this report if you want the fixtures updated.

The tool never touches the network: all page requests are blocked, and the offline browser only ever loads the sanitized copy of each file.

## The real wizard structure (validated 15 November 2026)

Validated from an owner-saved manual capture of the live form (`captures/manual/01-start.html`, processed offline by `docubye-google-report`; only the JSON report was used — never raw HTML):

- The wizard is a **single dynamic page (SPA)**. There are no per-step URLs; sections expand in place as radio options are selected. Saving the page twice yields identical files unless sections were expanded first.
- Structure: (a) reason radio list including "Content contains your personal information", plus country-of-residence dropdown; (b) info-type radio list (address/phone/email, bank account, credit card, government-ID document images, official records, login credentials, "Other personal information"); (c) a **conditional government-ID sub-section** (ID type radio, "Last four characters" field, issuing-country dropdown) that appears only for the ID option; (d) doxxing yes/no question; (e) contact email; (f) "Specific content URLs" textarea; (g) screenshots upload; (h) "Google Search results page URLs" textarea; (i) "Search terms" textarea.
- Validation result on the unexpanded start page: **6 selectors found** (the remodeled single-page-aware checks; the older two-step model found 4), the deeper conditional sections correctly absent until expanded, **CAPTCHA and login-wall correctly absent**, **26 asset requests blocked** by the offline guard.
- Selector validation is now single-page aware: a control present in the DOM but hidden counts as found, with visibility recorded (`found/hidden` vs `found/visible`). Fixtures under `tests/fixtures/google/` model this structure but remain hand-written synthetic content — no captured markup or values were copied.

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
