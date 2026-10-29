# Architecture proposal

**Status:** Synthetic workflow implemented; live-site integration remains blocked on a broader security review.

## Design goal

Make browser automation reliable enough for privacy-sensitive workflows without giving a general-purpose model unlimited authority over the user's browser, data, or identity.

## Current components

### 1. Workflow controller

The agent module owns the permitted workflow. It accepts only the exact 127.0.0.1 loopback origin, observes the page, requests a field mapping, prepares a review summary, waits for explicit approval, and records a bounded set of state transitions. The model does not decide whether the submission gate is open.

### 2. Browser driver and request guard

Playwright controls the browser. A context-level route handler:
- Allows only a small set of expected mock-site paths and methods.
- Blocks external hosts, including redirects, popup navigation, and external frames.
- Blocks POSTs to /submit without an active one-time approval.
- Requires the approved POST to be a main-frame document navigation.
- Compares the outgoing form payload against the exact in-memory payload shown for review.
- Consumes the approval before forwarding the first permitted submission, so a later request cannot reuse it.
- Blocks service workers for the prototype.

The guard is intended for a controlled local fixture. It is not a production-grade browser sandbox. Live-site integrations require a separate security review, more comprehensive navigation controls, and tests around redirects, popups, frames, downloads, browser protocols, and other page-initiated network paths.

### 3. Form planner

The planner module defines a protocol, an offline deterministic mapping, and an optional OpenAI Responses API mapper. The model receives only field metadata (name, label, input type, and required flag), never the profile's name, email, phone, cookies, or credentials. Model output is parsed and validated against an allowlist of input names and canonical profile fields.

AI is deliberately constrained to mapping fields in this milestone. It does not have arbitrary browser tools, cannot choose a destination, and cannot approve a submission. A future AI-navigation layer must remain behind an independently enforced navigation boundary.

### 4. Synthetic mock site

The mock-site module serves the form and scenarios for human verification, unexpected requests, pre-approval submission, outbound requests, redirects, popups, external frames, changed form destinations, changed payloads, and duplicate attempts after approval. All test personal data is synthetic.

### 5. Task state and evidence

The models module implements a typed state machine and a one-time submission-attempt guard. Public task records contain timestamps, generic action descriptions, status, and a task ID—not profile values or full page content. The verified-removed state is only reached when the fixture's separate verification endpoint confirms removal.

## Proposed tools

- Python 3.11+
- Playwright for browser control and end-to-end testing
- pytest for workflow and safety tests
- SQLite later, once task records need persistence; current task state is in memory
- Optional OpenAI SDK for model-assisted field mapping

## Before connecting to a real source

1. Verify CI for the full browser suite after the expanded request-guard tests.
2. Review and test redirects, popup tabs, frames, downloads, browser protocols, request bodies, and navigation changes.
3. Choose one official removal workflow and document its terms, eligibility, required fields, verification method, and human checkpoints.
4. Implement a source-specific adapter rather than allowing arbitrary model-generated clicks.
5. Keep pre-submission review and explicit approval enabled until the integration has adequate safety evidence.
