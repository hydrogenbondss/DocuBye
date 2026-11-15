"""Manual-capture report tool for the Google contact-removal flow.

The automated live-capture path is abandoned: Google stonewalls
automation-controlled browsers at sign-in, and DocuBye's no-evasion
principles mean we will not fight that. Instead the OWNER does everything in
their own everyday browser — sign in, open the removal form, walk its steps
manually, and save each step as "Webpage, HTML Only" into a local folder,
named in order (01-start.html, 02-form.html, ...).

This tool reads those local files ONLY: no live network, no sign-in, no
browser automation against Google. It loads each sanitized file offline
(set_content, all requests blocked), runs the existing selector validation,
shows a redaction summary (counts and types, never values), and offers an
opt-in sanitized copy. The output is a machine-readable JSON report with no
page content and no personal values.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .google_capture import SelectorCheck, sanitize_html, validate_selectors

DEFAULT_SAVE_DIR = "captures/google-manual"


@dataclass(slots=True)
class ReportResult:
    processed_files: list[str] = field(default_factory=list)
    saved_files: list[str] = field(default_factory=list)
    checks: list[SelectorCheck] = field(default_factory=list)
    blocked_requests: int = 0
    notes: list[str] = field(default_factory=list)

    def report(self) -> dict[str, object]:
        return {
            "processed_files": self.processed_files,
            "saved_files": self.saved_files,
            "selector_checks": [
                {"step": c.step, "selector": c.description, "status": c.status, "visibility": c.visibility}
                for c in self.checks
            ],
            "blocked_requests": self.blocked_requests,
            "notes": self.notes,
        }


def build_html_report(
    html_dir: str | Path,
    *,
    save_dir: str | Path = DEFAULT_SAVE_DIR,
    prompt_fn: Callable[[str], str] = input,
    headless: bool = True,
) -> ReportResult:
    """Process owner-saved HTML snapshots in name order. Offline only."""
    source = Path(html_dir)
    if not source.is_dir():
        raise ValueError(f"Not a directory: {source}")
    files = sorted(source.glob("*.html"))
    if not files:
        raise ValueError(f"No .html files found in {source}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install dependencies with: pip install -e '.[dev]'") from exc

    result = ReportResult()
    save_target = Path(save_dir)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(service_workers="block")

        def block_everything(route) -> None:
            # Offline guarantee: saved pages reference external assets; none may load.
            result.blocked_requests += 1
            route.abort("blockedbyclient")

        context.route("**/*", block_everything)
        page = context.new_page()
        try:
            for index, file in enumerate(files):
                step = file.stem
                raw = file.read_text(encoding="utf-8", errors="replace")
                sanitized, applied = sanitize_html(raw)
                # Counts and types only — never the redacted values.
                print(f"{file.name}: redacted {', '.join(applied) or 'nothing'}")

                decision = prompt_fn(
                    f"Save a sanitized copy of {file.name}? Type 'save' to keep it: "
                )
                if decision.strip().casefold() == "save":
                    save_target.mkdir(parents=True, exist_ok=True)
                    path = save_target / f"{index + 1:02d}-{file.name}"
                    path.write_text(sanitized, encoding="utf-8")
                    result.saved_files.append(str(path))

                # The offline browser only ever sees the sanitized version.
                page.set_content(sanitized)
                page.wait_for_timeout(50)
                result.checks.extend(validate_selectors(page, step))
                result.processed_files.append(file.name)

            result.notes.append(
                f"Processed {len(result.processed_files)} file(s) offline; "
                f"{result.blocked_requests} asset request(s) blocked. "
                "No live network, no sign-in, no submission."
            )
            return result
        finally:
            context.close()
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate owner-saved HTML captures of the Google removal wizard. Offline only."
    )
    parser.add_argument("--html-dir", required=True, help="Folder of owner-saved .html files, named in step order")
    parser.add_argument("--save-dir", default=DEFAULT_SAVE_DIR, help="Gitignored directory for opt-in sanitized copies")
    args = parser.parse_args()
    result = build_html_report(args.html_dir, save_dir=args.save_dir)
    print("\nSelector validation report (no page content):")
    print(json.dumps(result.report(), indent=2))


if __name__ == "__main__":
    main()
