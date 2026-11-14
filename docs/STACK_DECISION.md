# Stack decision record

**Status:** Accepted for Milestone 1. Revisit before Milestone 2 introduces live-site adapters.

## Decision

- **Language:** Python, `requires-python = ">=3.11"`.
- **Browser automation:** Playwright (Chromium) for both the workflow and end-to-end tests.
- **Tests:** pytest, run in GitHub Actions on every push and pull request.
- **Persistence:** SQLite via the Python standard library (`sqlite3`).
- **Data models:** standard-library dataclasses and enums.
- **Packaging:** setuptools with `pip install -e '.[dev]'`.

## Intentional deviations and why

- **Python 3.11+ rather than 3.12-only.** CI runs 3.12, but the package declares 3.11 as the floor so contributors on slightly older system Pythons can run the suite. Nothing in the codebase requires 3.12-only features. Revisit if a 3.12 feature becomes load-bearing.
- **pip + venv rather than uv.** The project uses the standard-library virtual environment workflow every Python installation already has. There is no lockfile yet; dependency ranges are small and CI installs fresh each run. Revisit when dependency resolution becomes a support burden.
- **Dataclasses rather than Pydantic-style schemas.** The only runtime dependency is Playwright, and the schemas in this milestone are small, internal, and validated explicitly where they cross trust boundaries (the route guard, the state machine, the store). Adding a validation framework now would cost a dependency without changing the safety properties. Revisit if external input parsing grows.

## Consequences

- Contributors need only Python, pip, and Playwright's Chromium.
- Task evidence stays in a local SQLite file with no server process.
- Any future dependency addition must be justified against the local-first, minimal-supply-chain goals in the product brief.
