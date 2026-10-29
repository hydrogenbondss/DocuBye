# First-source review: Google Search personal contact information

**Status:** Research and request-contract preparation only; no live browser adapter or submission path exists.  
**Source type:** Search-result removal, not removal from the website hosting the content.

## Official entry points

- Removal form: https://support.google.com/websearch/contact/content_removal_form?hl=en
- Google Help: https://support.google.com/websearch/answer/9673730?hl=en
- Help for finding and removing personal contact information: https://support.google.com/websearch/answer/12719076?hl=en

## Result of live non-submitting inspection (30 October 2026)

The official form was opened in a fresh, unauthenticated browser context. The visible top-level controls were: the radio choices for “Content contains nudity or sexual material,” “Content contains your personal information,” “Content is on a site with exploitative removal practices,” and “Content shows a person under 18”; a required country-of-residence dropdown (showing United States by default); a reCAPTCHA element; and a Next button.

The “Content contains your personal information” radio was selected during the inspection. The expected “Address, phone number, and/or e-mail address” choice did **not** become visible at that stage. The Next button was not clicked, no personal values were entered, no account sign-in was used, and nothing was submitted. Because a CAPTCHA was visible before the next step, DocuBye will not advance automatically or attempt to bypass it.

**Conclusion:** the active sub-branch and its required fields remain unverified. The earlier request contract is a provisional data model based on public Help text and the form document, not a selector map for the live UI. No real-source adapter should be implemented until a person can safely take over the verification step, without entering personal data or submitting a request.

## What the official form currently shows

The public form starts by asking what kind of personal-content removal is requested and the country of residence. Within the personal-information path, it offers a narrow option for **address, phone number, and/or email address**; other options include government IDs, bank/credit-card details, official records, login credentials, and other personal information. DocuBye must not allow the model to choose a broader category.

The form text currently exposes fields for the exact contact value as shown on the page, source content URL(s), Google Search results page URL(s), search terms, additional context, and a final accuracy/authority attestation. It also contains country and contact-information prompts. The public help says Google needs context and contact information and may preserve content considered to be in the public interest.

**Inspection limitation:** This was a non-submitting inspection of the public page text. The page includes multiple conditional report branches in the same document, so this does not prove which fields are visible or required after the contact-info branch is selected. An interactive, non-submitting inspection of the active branch is still required before implementing selectors or enabling an adapter. Do not infer visible form state from the full document text.

## Narrow intended scope

Support only a user's own address, phone number, or email address appearing at URLs they supply or confirm. Do not start with government IDs, bank/card numbers, credentials, medical records, intimate imagery, minors, legal claims, exploitative-removal claims, or other categories. These require separate risk and policy reviews.

The selected category and value must come from the user, not model inference. Google says to enter the contact information as it appears on the page; the form also requests specific content URL(s) and Google Search results page URL(s). Search terms and additional context may be requested. The final accuracy/authority statement is a human attestation and must never be completed or asserted by the model on the user's behalf.

## What this workflow does and does not do

This is a request to delist a Google Search result. It does **not** delete the original page or remove the information from other search engines, copies, archives, or other sites. Google reviews requests and may approve, deny, or partially limit removal where public-interest considerations apply.

Google Help documents a separate “Results about you” experience for monitoring home-address, phone, and email matches; availability varies by market, and the account-based flow requires sign-in. DocuBye should not assume that the public form and the account-based flow are interchangeable.

## Request contract added to DocuBye

The module src/docubye/sources/google_search_contact.py contains a pure request draft/review contract for the narrow contact-info workflow. It does not drive a browser and cannot submit a request. The command docubye-inspect-google-form is a separate read-only inspector: it can select the visible branch and collect field metadata, but blocks non-GET requests and does not fill or submit anything.

The contract validates:
- One supported contact-info category and the exact exposed value.
- One or more source page URLs.
- One or more Google Search results URLs and search terms.
- Country of residence and a contact email for the draft.
- No embedded URL credentials, local hostnames, private/reserved IPs, or out-of-scope categories.
- A redacted operational record that excludes raw values, URLs, email addresses, and search terms.
- An approval object bound to the exact request fingerprint, requiring separate affirmative accuracy, authority, and search-delisting acknowledgements; the approval can only be consumed once.

These checks validate request structure; they do **not** determine legal eligibility, prove that a removal request should be granted, or confirm that the live form's exact field requirements have been mapped.

## Next steps before a real adapter

1. Run a non-submitting interactive inspection of the active contact-info branch on the official form, with no real profile loaded.
2. Record the exact visible required fields, their stable labels/attributes, whether any account login is needed, and all branch decisions.
3. Build deterministic, source-specific field filling; keep actual values out of model prompts and ordinary logs.
4. Present the full destination, category, exposed value, source URLs, Search result URLs, terms, country, contact channel, and any context/screenshot that will be sent for human review.
5. Require a fresh explicit approval tied to that exact review; pause on any CAPTCHA, login, identity check, new declaration, changed destination, or unrecognised field.
6. Keep automated tests synthetic and non-submitting. No live requests in CI.
7. After a user-authorised live submission, record receipt separately from Google's decision and separately verify whether the Search result actually disappeared.

## Sources checked

- Google's [official personal-content removal form](https://support.google.com/websearch/contact/content_removal_form?hl=en), inspected 30 October 2026.
- Google's [personal-info Search-removal guidance](https://support.google.com/websearch/answer/12719076?hl=en), inspected 30 October 2026.
- Google's [general removal guidance](https://support.google.com/websearch/answer/9673730?hl=en), inspected 30 October 2026.
