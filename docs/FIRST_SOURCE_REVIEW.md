# First-source review: Google Search personal-information removal

**Status:** Candidate selected for the next milestone; not yet implemented or live-tested by DocuBye.  
**Source type:** Search-result removal, not removal from the website hosting the content.

## Official entry points

- Removal form: https://support.google.com/websearch/contact/content_removal_form?hl=en
- Google Help: https://support.google.com/websearch/answer/9673730?hl=en
- Help for finding and removing personal contact information: https://support.google.com/websearch/answer/12719076?hl=en

## Why this is a reasonable first real-source candidate

Google provides an official public form for reporting personal information that appears in Google Search. The documented form asks the reporter to choose the type of removal request and country of residence. The personal-information branch covers address, phone number, email address, government IDs, financial account details, and other sensitive categories. Google requires the specific content URL(s); additional details and contact information are used to assess the report and provide updates.

For DocuBye's first real-source adapter, restrict scope to **a user's own address, phone number, or email address appearing in a supplied page URL**. Do not start with government IDs, bank/card numbers, login credentials, medical records, intimate imagery, minors, legal claims, or exploitative-removal claims. Those branches need different policy and data-handling review.

## What this workflow does and does not do

Google may remove a URL fully or partially from Google Search after reviewing a request. That does **not** delete the content from the original website, other search engines, copied pages, or archives. Google may reject content that it considers important or newsworthy. DocuBye must report Google’s decision separately from independently checking whether the result has disappeared.

Official Help says the request needs the URL of the page containing the information, and only the URLs supplied are reviewed. It also notes that some removals may be partial and the original page can remain available elsewhere.

## Proposed data contract

Required from the user for this narrow adapter:

- One or more exact page URLs supplied or confirmed by the user.
- Which exposed contact-info category is present: address, phone, or email.
- The exact exposed value needed by Google's form.
- Country of residence, if required by the live form.
- A contact email if the user wants status updates and the form requires it.

Do not ask DocuBye's AI model to infer or reconstruct a user's private values from pages. The agent should use values the user explicitly provided or reviewed. No identity document or unrelated sensitive field should be requested for this narrow path.

## Proposed browser workflow

1. Open only the verified official Google form.
2. Confirm that the displayed workflow is the expected personal-information branch. If the form differs, pause rather than guessing.
3. Use Playwright to navigate the form and fill supported fields. AI may assist in interpreting labels, but it must not choose the user's policy category, invent data, or decide the request is legally eligible.
4. Display a final review containing the Google destination, supplied URLs, contact-info category, and categories of data to be sent. Do not expose full values to ordinary logs.
5. Submit only after the user explicitly approves the exact request. Any CAPTCHA, account challenge, identity check, unexpected disclosure, or policy attestation pauses for human intervention.
6. Capture a minimal receipt/status reference. Do not call the request removed until Google's decision and a suitable verification step support that status.

## Tests required before release

- Mirror the narrow form branch with synthetic data and test field mapping and the approval gate.
- Verify redirects and new windows remain within the exact approved Google form workflow.
- Ensure request URLs and field values match the review snapshot.
- Test rejection, timeout, interrupted submission, duplicate-submit prevention, and resume behavior.
- Test that the agent pauses if Google changes form layout, required fields, terms, or destination.
- Verify that logs and screenshots redact personal values.
- Conduct a non-submitting browser inspection of the live official form before enabling a real-source adapter. Never run that inspection with a real user profile or submit any form as part of automated tests.

## Source notes

This review is based on the linked official Google form and Help Center pages checked on 30 October 2026. The form is dynamic and may change; verify the live page again during implementation.
