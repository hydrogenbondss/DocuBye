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

## Guarded human-handoff mode

The inspector now supports:

    docubye-inspect-google-form --headed --human-handoff

This launches a fresh, unauthenticated visible browser and pauses in the terminal for a person to inspect the public form. The person may select navigation choices but must stop before data-entry fields; they must not sign in, enter personal information, upload files, or click Submit. On return, DocuBye records only selected radio labels, visible field names/types/labels/placeholders/required/disabled flags, visible button labels, and blocked-request method/host/path metadata. The report omits input values, cookies, request bodies, screenshots, query strings, and fragments.

The handoff uses the same network guard as automatic inspection. It allows only HTTPS GET/HEAD requests to the explicit Google host allowlist; it blocks all other methods, unapproved hosts, WebSockets, and known submission paths. This is intentionally restrictive. A CAPTCHA verification request or wizard transition that requires POST may remain blocked, in which case the branch remains unverified. The handoff is an observation aid, not a CAPTCHA workaround and not a form-submission capability. Do not relax the guard merely to advance the wizard.

**Guarded handoff attempt (31 October 2026):** the user ran the command from a fresh local checkout. The browser page did not load into a usable form, and the capture ended with `TargetClosedError`. The report contained no selected steps, visible fields, or visible buttons. It recorded blocked requests to Google font/telemetry services, the support-site feedback endpoint, and account/widget services. No personal values were entered, no fields were filled, and nothing was submitted. This is a failed Playwright handoff attempt, not evidence that the contact-info branch is inaccessible or that any particular blocked request is required by the form. The current policy intentionally blocks all POST requests, so the wizard may not function fully under this guard. Do not whitelist POST traffic or weaken the guard simply to make the page render.

## Latest manual observation of the active contact-info branch (31 October 2026)

After the guarded Playwright handoff failed to render a usable page, the user opened the official form directly in a regular browser and selected **“Content contains your personal information.”** The form then displayed the heading **“Request removal of content containing personal information from Google Search”** and the following live labels/prompts:

- Required selector: **“Select the personal information you would like removed from Google search results.”**
- Required value field: **“Enter your address, phone number, or e-mail address as they appear in the webpage(s).”** The form text says that if multiple types of contact information appear in the result, only one needs to be included.
- Required email field: **“Your e-mail address as it appears in the webpage(s).”**
- Required question: **“Is there malicious or threatening intent expressed directly in the content on the URL or domain (this practice is sometimes known as doxxing)?”**
- The page also offers an email follow-up feedback choice: Google may ask for feedback about the support experience after the case is closed.

The user shared field labels only. No contact values, email addresses, IDs, or other personal data were entered or disclosed in the conversation; no file was uploaded and nothing was submitted.

**What this verifies:** the personal-information route reaches a contact-information form state and exposes the address/phone/email value prompt. This is meaningful live UI evidence for the intended source.

**What remains unverified:** the exact options inside the required personal-information selector; the answer choices for the doxxing question; all lower-page prompts (including any source URL, Search URL, search-term, context, and declaration fields); stable DOM selectors and input attributes; and whether any further navigation, login, or human-verification step is required. The manually observed browser session is not the same as a successful run of DocuBye's headed Playwright inspector. Do not mark the inspector or a live adapter as complete based on this partial observation.

## What the official form currently shows

The public form starts by asking what kind of personal-content removal is requested and the country of residence. Within the personal-information path, it offers a narrow option for **address, phone number, and/or email address**; other options include government IDs, bank/credit-card details, official records, login credentials, and other personal information. DocuBye must not allow the model to choose a broader category.

The form text currently exposes fields for the exact contact value as shown on the page, source content URL(s), Google Search results page URL(s), search terms, additional context, and a final accuracy/authority attestation. It also contains country and contact-information prompts. The public help says Google needs context and contact information and may preserve content considered to be in the public interest.

**Inspection limitation:** The current public page content exposes the address/phone/email option and associated field labels, but it contains multiple conditional report branches in one document. It does not prove which fields are visible or required after that option is selected. The 31 October headed browser attempt did not capture a usable UI state. An interactive, non-submitting inspection of the active branch is still required before implementing selectors or enabling an adapter. Do not infer visible form state from the full document text.

## Narrow intended scope

Support only a user's own address, phone number, or email address appearing at URLs they supply or confirm. Do not start with government IDs, bank/card numbers, credentials, medical records, intimate imagery, minors, legal claims, exploitative-removal claims, or other categories. These require separate risk and policy reviews.

The selected category and value must come from the user, not model inference. Google says to enter the contact information as it appears on the page; the form also requests specific content URL(s) and Google Search results page URL(s). Search terms and additional context may be requested. The final accuracy/authority statement is a human attestation and must never be completed or asserted by the model on the user's behalf.

## What this workflow does and does not do

This is a request to delist a Google Search result. It does **not** delete the original page or remove the information from other search engines, copies, archives, or other sites. Google reviews requests and may approve, deny, or partially limit removal where public-interest considerations apply.

Google Help documents a separate “Results about you” experience for monitoring home-address, phone, and email matches; availability varies by market, and the account-based flow requires sign-in. DocuBye should not assume that the public form and the account-based flow are interchangeable.

## Request contract added to DocuBye

The module src/docubye/sources/google_search_contact.py contains a pure request draft/review contract for the narrow contact-info workflow. It does not drive a browser and cannot submit a request. The command docubye-inspect-google-form is a separate read-only inspector: automatic mode collects visible field metadata but stops before branch selection if a visible CAPTCHA/human-verification element is present. Its headed human-handoff mode allows manual observation under the same guard. Both modes permit only GET/HEAD requests to the explicit host allowlist, block unapproved hosts and WebSockets, and do not fill or submit anything.

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

1. Complete the user's manual, non-submitting inspection of the contact-info branch by recording the selector's exact choices, the doxxing question's answer choices, and all lower-page prompts. Do not enter personal values.
2. Diagnose why the headed Playwright handoff failed to render a usable page. Preserve the no-submission boundary; do not weaken the route guard or whitelist arbitrary POST traffic to continue.
3. Record stable labels/attributes and required flags using a safe, non-submitting technical inspection method; verify whether any account login or human-verification step is required.
3. Build deterministic, source-specific field filling only after the live branch is confirmed; keep actual values out of model prompts and ordinary logs.
4. Present the full destination, category, exposed value, source URLs, Search result URLs, terms, country, contact channel, and any context/screenshot that will be sent for human review.
5. Require a fresh explicit approval tied to that exact review; pause on any CAPTCHA, login, identity check, new declaration, changed destination, or unrecognised field.
6. Keep automated tests synthetic and non-submitting. No live requests in CI.
7. After a user-authorised live submission, record receipt separately from Google's decision and separately verify whether the Search result actually disappeared.

## Sources checked

- Google's [official personal-content removal form](https://support.google.com/websearch/contact/content_removal_form?hl=en), manually inspected by the user in a regular browser on 31 October 2026; the guarded Playwright handoff attempted the same day did not render a usable form.
- Google's [personal-info Search-removal guidance](https://support.google.com/websearch/answer/12719076?hl=en), inspected 30 October 2026.
- Google's [general removal guidance](https://support.google.com/websearch/answer/9673730?hl=en), inspected 30 October 2026.
