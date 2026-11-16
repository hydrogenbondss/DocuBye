# Integration: PeopleConnect Suppression Center (guided, owner-executed)

**Status:** Guided flow implemented. **The tool guides and tracks; the owner submits.** There is no browser automation, no network access in this code path, and no CAPTCHA bypass. PeopleConnect refuses authorized-agent submissions, so owner-executed is the **only** route — guided-only by design, not by limitation.  
**Last tested:** not yet tested against the live site — owner rehearsal pending.

One suppression covers Intelius, TruthFinder, Instant Checkmate, US Search, ZabaSearch, and other PeopleConnect brands. **Suppression is NOT deletion of the underlying records.**

## Workflow

1. **Profile** — the owner writes contact email, legal name, and date of birth (YYYY-MM-DD) into a gitignored profile file (e.g. `captures/profile.local.json`; synthetic example at `tests/fixtures/peopleconnect/owner_profile.example.json`). Never commit a real profile. The date of birth is displayed in the terminal packet only and is never written to events, the store, logs, or recorded output.
2. **Submit** — `docubye submit-peopleconnect <task-id> --profile <path>` walks the packet in the terminal:
   - *Before you start* — use an email alias if available; plan one sitting; the emailed sign-in link expires in ~15 minutes.
   - *Sign in* — https://suppression.peopleconnect.us/login, enter contact email, click the emailed link within ~15 minutes (check spam; expiry is normal — restart).
   - *Match your record* — enter legal name and DOB exactly as in public records; select the matching record.
   - *Suppress* — set the record's visibility / "Desired Behavior" dropdown to "Suppressed" and save. **Never delete the Suppression Center account afterwards** — deleting it erases the standing suppression instruction while the data pipeline keeps flowing.
   - *Keep in mind* — brand coverage, suppression ≠ deletion, up to 10 business days to propagate, re-check every 3–6 months.
3. Recording happens only after the typed gate (`I SUBMITTED`); approval is consumed exactly once; a changed profile after approval requires a fresh review.
4. **Verify** — `docubye verify <task-id> --evidence <path> --confirm` with an artifact under gitignored `captures/evidence/`.

## Required data

Contact email, first name, last name, date of birth (YYYY-MM-DD). Optional: middle name, previous names (used only for record-matching guidance).

## Verification method

PeopleConnect suppression is **not publicly self-verifiable** — their people-search reports are paid. "Suppressed" means exactly this: the portal shows the record as Suppressed and/or a confirmation email was received. It does **not** prove the underlying data was deleted.

## Failure states

| Condition | Behaviour |
|---|---|
| Expired sign-in link | Normal — links last ~15 minutes; restart the sign-in step |
| Verification code only deliverable to an old email/phone | Stop the online flow; email privacy@peopleconnect.us or call (800) 699-8081 with name, DOB, and the addresses on the listing |
| Region restriction | PeopleConnect states the tool is intended for US residents; non-US owners may not be able to proceed |
| Re-listing under name variants or new addresses | Expected over time; re-check every 3–6 months and repeat the flow |
| Account deleted after suppressing | Self-defeating: deletion erases the standing suppression while ingestion continues. Never delete the account. |
| Changed profile after approval | Fingerprint mismatch; fresh review required |
| Walkthrough interrupted | Task resumes with the same approval; nothing is recorded without the typed gate |
