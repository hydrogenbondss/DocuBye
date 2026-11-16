# Integration: Whitepages suppression (guided, owner-executed, phone verification)

**Status:** Guided flow implemented. **The tool guides and tracks; the owner submits.** There is no browser automation against whitepages.com, no network access in this code path, and no CAPTCHA bypass.  
**Last tested:** not yet tested against the live site — owner rehearsal pending.

## Workflow

1. **Discovery (owner, manual):** search whitepages.com for your name and city/state variants in your own browser; copy each matching profile URL into your gitignored profile file (e.g. `captures/profile.local.json`; synthetic example at `tests/fixtures/whitepages/owner_profile.example.json`). Never commit a real profile.
2. **Submit** — `zwip submit-whitepages <task-id> --profile <path>` validates the profile (https listing URLs on whitepages.com/www.whitepages.com only; a phone number that can receive a live call is required — the standard flow cannot complete without one), then walks the packet:
   - *Find your listings* — search guidance (URLs come from the validated profile).
   - *Before you start* — the flow places a **live automated call** with a 4-digit code; have your phone next to you and finish one listing at a time. A secondary number (e.g. Google Voice) works if you prefer not to share your primary one.
   - *Opt out of each listing* — per listing URL: https://www.whitepages.com/suppression-requests → paste URL → "Remove Me" → pick a reason → enter the phone number → answer the call → enter the 4-digit code yourself.
   - *Confirm* — removals process within ~1–72 hours; re-check each listing URL after 72 hours.
   - *Keep in mind* — re-listing is common (re-check quarterly); if the form rejects your number or cites too many requests, use the manual route: privacyrequest@whitepages.com with your listing URLs, or their privacy webform.
3. The packet (including the phone number) is displayed in the terminal only — never written to disk, logged, or stored. Recording happens only after the typed gate (`I SUBMITTED`); the approval is consumed exactly once; a changed profile after approval requires a fresh review.
4. **Verify** — `zwip verify <task-id> --evidence <path> --confirm` with an artifact under gitignored `captures/evidence/`.

## Required data

Contact email, phone number (live-call capable), and at least one listing URL. Optional: first/last name, city, state (discovery guidance only).

## Verification method

Whitepages **is publicly self-verifiable**: re-search the listing URL after ~72 hours. **"Removed" means exactly this: the listing URL no longer shows the profile on re-search — nothing more.** Suitable evidence: a screenshot of the empty re-search result taken after 72 hours, and/or the confirmation communication.

## Failure states

| Condition | Behaviour |
|---|---|
| Phone number rejected by the form | Use a secondary number, or the manual route (privacyrequest@whitepages.com / privacy webform) |
| "Too many suppression requests" | Manual route: email with listing URLs, or the privacy webform |
| No phone that can receive a live call | The standard online flow cannot complete; use the email/webform route |
| Multiple listings | Each needs its own request; the packet iterates all of them, one at a time |
| Re-listing | Common — new data ingestion resurfaces records; re-check quarterly |
| Changed profile after approval | Fingerprint mismatch; fresh review required |
| Walkthrough interrupted | Task resumes with the same approval; nothing is recorded without the typed gate |
