# DocuGone

**An open-source AI agent for removing your own digital footprint.**

DocuGone aims to do more than list privacy risks or generate opt-out instructions. It is being designed to carry out authorised removal workflows in a real browser, handle routine steps automatically, ask for help when a site requires human judgement, and keep an honest record of what happened.

> **Project status: early planning.** No working browser agent or removal integrations have been implemented yet. The roadmap starts with a controlled test workflow before any live removal submissions.

## The intended experience

1. **Find** — identify an exposure from a user-provided URL or a supported source.
2. **Understand** — determine what information is exposed and which removal path is available.
3. **Act** — navigate the site's official workflow, fill the appropriate fields, and perform the steps the user has authorised.
4. **Escalate** — pause for CAPTCHA, identity checks, legal attestations, unexpected requests, or other steps that require the person.
5. **Verify** — track the outcome and distinguish a sent request from a confirmed removal.

## Principles

- **The user owns the task.** Work only on the user's own information or information they are authorised to manage.
- **Local-first.** Keep browser sessions and task records on the user's machine by default. Clearly disclose any data sent to a remote model or service.
- **Human control without busywork.** The user authorises the scope; the agent handles routine steps within that scope and stops when the action falls outside it.
- **Evidence over promises.** A request being submitted is not proof that information was deleted.
- **No evasion.** Do not bypass CAPTCHAs, access controls, identity checks, or a site's explicit human-verification steps.
- **Minimise sensitive data.** Do not log personal fields, cookies, credentials, or full page contents unnecessarily.

## Development

Read these before implementation:

- [Product brief](docs/PRODUCT_BRIEF.md) — problem, intended user experience, scope, and guardrails.
- [Architecture proposal](docs/ARCHITECTURE.md) — recommended components and technical decisions.
- [Roadmap](docs/ROADMAP.md) — incremental milestones and acceptance criteria.

The first technical milestone is a simulated removal workflow using synthetic data. It must prove that DocuGone can navigate a form, map fields correctly, pause for an approval gate, record evidence, and report status accurately before it is connected to real personal information.

## What DocuGone cannot promise

No tool can guarantee that every trace of a person will disappear from the internet. Some information cannot be removed, some sources have lawful retention requirements, and copies may persist outside the original site's control. DocuGone should report limitations plainly and never label a request "removed" without adequate verification.

## Contributing

The project is at the design stage. Please open an issue before contributing a new integration or proposing a significant architectural change. Every integration should document the supported workflow, required data, verification method, failure states, and the last date it was tested.

## Licence

MIT. See [LICENSE](LICENSE).
