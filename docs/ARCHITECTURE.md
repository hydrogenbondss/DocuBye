# Architecture proposal

**Status:** Synthetic workflow implemented with durable, restart-safe recovery. Live-site integration remains blocked on a broader security review; first-source research and model-assisted field mapping live on separate draft branches.

## Design goal

Make browser automation reliable enough for privacy-sensitive workflows without giving a general-purpose model unlimited authority over the user's browser, data, or identity.

## Current components

### 1. Workflow controller

The agent module owns the permitted workflow. It accepts only the exact 127.0.0.1 loopback origin, observes the page, requests a field mapping, prepares a review summary, waits for explicit approval, and records a bounded set of state transitions. No model decides whether the submission gate is open.

### 2. Browser driver and request guard

Playwright controls the browser. A context-level route handler:
- Allows only a small set of expected mock-site paths and methods.
- Blocks external hosts, including redirects, popup navigation, and external frames.
- Blocks POSTs to /submit without an active one-time approval.
- Requires the approved POST to be a main-frame document navigation.
- Compares the outgoing form payload against the exact in-memory payload shown for review.
- Consumes the approval before forwarding the first permitted submission, so a later request cannot reuse it.
- Blocks service workers and routes WebSocket connections to a non-forwarding mock handler.

The guard is intended for a controlled local fixture. It is not a production-grade browser sandbox. Live-site integrations require a separate security review, more comprehensive navigation controls, and tests around downloads, browser protocols, and remaining navigation edge cases.

### 3. Form planner

The planner module defines a protocol and an offline, deterministic rule-based mapping. The deterministic path is the milestone baseline: it must be proven before any model-assisted variant is considered. This branch adds the optional OpenAI Responses API mapper on top of that baseline. The model receives only field metadata (name, label, input type, required flag), never profile values, cookies, or credentials, and its output is parsed and validated against an allowlist of input names and canonical profile fields. The model does not have browser tools, cannot choose a destination, and cannot approve a submission. Any future AI-navigation layer must remain behind an independently enforced navigation boundary.

### 4. Synthetic mock site

The mock-site module serves the form and scenarios for human verification, unexpected requests, pre-approval submission, outbound requests, redirects, popups, external frames, changed form destinations, changed payloads, duplicate attempts after approval, and an acknowledgement timeout after a recorded POST. All test personal data is synthetic and loaded from a fixture file.

Submissions are idempotent: the mock derives a submission key from the exact form payload, issues a confirmation ID once per key, and replays the same confirmation for repeated POSTs without counting them twice. A read-only /status endpoint looks up submissions by key, which is what makes recovery without resubmission possible.

### 5. Task state, persistence, and recovery

The models module implements a typed state machine and a one-time submission-attempt guard. Public task records contain timestamps, generic action descriptions, status, and a task ID—not profile values or full page content. The verified-removed state is only reached when the fixture's separate verification endpoint confirms removal.

The store module persists each task in SQLite: task ID, full event history, approval state, submission (idempotency) key, and confirmation ID. Approval consumption is atomic and survives process restarts, so an approval can never be used twice, even by a new process reopening the same store file.

An interrupted submission ends in UNKNOWN. The only exit from UNKNOWN is the recovery path: a read-only GET to the mock /status endpoint with the persisted idempotency key. If the original submission is found, its confirmation ID is recorded and the task moves to awaiting_confirmation. Automatic blind retry is disabled; recovery never sends a second POST.

## Proposed tools

- Python 3.11+
- Playwright for browser control and end-to-end testing
- pytest for workflow and safety tests
- SQLite (standard library) for task persistence
- See the [stack decision record](STACK_DECISION.md) for deliberate deviations and their rationale.

## Before connecting to a real source

1. Review and test redirects, popup tabs, frames, downloads, browser protocols, request bodies, and navigation changes.
2. Choose one official removal workflow and document its terms, eligibility, required fields, verification method, and human checkpoints.
3. Implement a source-specific adapter rather than allowing arbitrary model-generated clicks.
4. Keep pre-submission review and explicit approval enabled until the integration has adequate safety evidence.
