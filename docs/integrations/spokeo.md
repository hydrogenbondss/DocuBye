# Integration: Spokeo opt-out (guided, owner-executed)

**Status:** Guided submission implemented. **The tool guides and tracks; the owner submits.** There is no browser automation against spokeo.com and no network access in this code path.  
**Last tested:** not yet tested against the live site — packet built from the documented flow as of 2026-11; owner rehearsal pending.

## Workflow

1. **Discovery (owner, manual):** search spokeo.com for your name variants (and city/state) in your own browser; copy each matching listing URL into your gitignored profile file (e.g. `captures/profile.local.json`; synthetic example at `tests/fixtures/spokeo/owner_profile.example.json`). Never commit a real profile.
2. **Submit** — `docubye submit-spokeo <task-id> --profile <path>` validates the profile (every listing URL must be an `https://` URL on `spokeo.com` or `www.spokeo.com`; an empty listing list is rejected with instructions to run discovery first), then walks you through the packet in the terminal:
   - *Find your listings* — search guidance using your name/city/state variants (the actionable URLs come from the validated profile).
   - *Opt out of each listing* — for each listing URL, in order: go to https://www.spokeo.com/optout, paste the listing URL, enter your contact email, solve the CAPTCHA yourself, submit.
   - *Confirm by email* — Spokeo emails a verification link per request; the request is **not processed until you click that link**. Check spam/junk.
   - Closing note: listings can reappear as new data is ingested; re-check quarterly.
3. The packet is displayed in the terminal only — never written to disk, logged, or stored. Recording happens only after the typed gate (`I SUBMITTED`); the approval is consumed exactly once, and a changed profile after approval requires a fresh review.
4. **Verify** — `docubye verify <task-id> --evidence <path> --confirm` with an artifact under gitignored `captures/evidence/`.

## Required data

Contact email (used at opt-out and for the verification email) and at least one listing URL. Name/city/state are optional and used only for discovery guidance text.

## Verification method

Self-verifiable via public re-search: after Spokeo's processing window (about 72 hours), search for the listing URL again. **"Removed" means exactly this: the listing URL no longer shows the profile on re-check — nothing more.** Suitable evidence artifacts: a screenshot of the confirmation email and/or a screenshot of the empty re-search result taken after 72 hours, saved under `captures/evidence/`.

## Failure states

| Condition | Behaviour |
|---|---|
| Empty listing list | Rejected at profile validation; owner told to run discovery first |
| Non-Spokeo or non-https listing URL | Rejected at profile validation |
| Email link never clicked | Request is not processed by Spokeo; task stays `awaiting_confirmation` |
| CAPTCHA | Solved by the owner, never by the tool |
| Multiple listings | Each needs its own opt-out request; the packet iterates all of them |
| Reappearance from new data ingestion | Expected over time; re-check quarterly and repeat the flow |
| Changed profile after approval | Fingerprint mismatch; fresh review required |
| Walkthrough interrupted | Task resumes with the same approval; nothing is recorded without the typed gate |
