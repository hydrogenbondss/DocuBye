"""Command-line demo for DocuBye's synthetic workflow."""

from __future__ import annotations

import argparse
import json
import sys

from .agent import MockRemovalAgent, ReviewSummary, recover_submission, resume_paused_task
from .mock_site import running_mock_site
from .models import SyntheticProfile
from .planner import RuleBasedPlanner
from .store import TaskStore

SCENARIOS = ["normal", "challenge", "unexpected", "verified", "early-submit", "timeout-after-submit"]


def _approval_prompt(review: ReviewSummary) -> bool | None:
    print("\nSubmission review")
    print(f"Destination: {review.destination}")
    print("Data categories: " + ", ".join(review.data_categories))
    print("Profile values are synthetic and remain inside the local fixture.")
    answer = input("Submit this synthetic request? Type 'yes' to approve: ").strip().casefold()
    return answer == "yes"


def _run(args: argparse.Namespace) -> None:
    store = TaskStore(args.store)
    try:
        with running_mock_site(args.scenario, state_path=args.fixture_state) as (base_url, state):
            print(f"DocuBye mock site: {base_url}")
            print(f"Task store: {args.store}")
            print("Local synthetic data only. No real removal site will be contacted.")
            result = MockRemovalAgent(planner=RuleBasedPlanner(), headless=not args.headed).run(
                base_url=base_url,
                profile=SyntheticProfile(),
                approval_callback=_approval_prompt,
                store=store,
            )
            print("\nResult: " + result.message)
            print(json.dumps(result.task.to_public_dict(), indent=2))
            print(f"Synthetic fixture submissions: {state.submission_count}")
            if result.blocked_hosts:
                print("Blocked external hosts: " + ", ".join(sorted(set(result.blocked_hosts))))
            print(f"Pre-approval submissions blocked: {result.blocked_submission_attempts}")
            if result.task.status.value == "unknown":
                print(f"Recover with: docubye recover {result.task.task_id} --store {args.store}")
    finally:
        store.close()


def _recover(args: argparse.Namespace) -> None:
    store = TaskStore(args.store)
    try:
        with running_mock_site(args.scenario, state_path=args.fixture_state) as (base_url, state):
            stored = recover_submission(base_url, store, args.task_id)
            print(json.dumps(stored.task.to_public_dict(), indent=2))
            print(f"Confirmation ID: {stored.confirmation_id or 'none found'}")
            print(f"Synthetic fixture submissions: {state.submission_count} (no second request was sent)")
    finally:
        store.close()


def _resume(args: argparse.Namespace) -> None:
    store = TaskStore(args.store)
    try:
        stored = resume_paused_task(
            store, args.task_id, args.note, human_confirmed=args.confirm_human_resolution
        )
        print(f"Task resumed to {stored.task.status.value}. Re-run the workflow to re-inspect and review before any submission.")
        print(json.dumps(stored.task.to_public_dict(), indent=2))
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DocuBye's local synthetic removal demo")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the synthetic removal workflow")
    run_parser.add_argument("--scenario", choices=SCENARIOS, default="normal")
    run_parser.add_argument("--store", default="docubye-tasks.sqlite3", help="SQLite task store path")
    run_parser.add_argument(
        "--fixture-state", default="docubye-fixture-state.json",
        help="Mock-site state file, so `docubye recover` can find submissions from earlier runs",
    )
    run_parser.add_argument("--headed", action="store_true", help="Show the local browser window")
    run_parser.set_defaults(handler=_run)

    recover_parser = subparsers.add_parser(
        "recover",
        help="Resolve an UNKNOWN task by looking up its original submission (read-only, never resubmits)",
    )
    recover_parser.add_argument("task_id")
    recover_parser.add_argument("--store", default="docubye-tasks.sqlite3", help="SQLite task store path")
    recover_parser.add_argument(
        "--fixture-state", default="docubye-fixture-state.json",
        help="Mock-site state file written by the original `docubye run`",
    )
    recover_parser.add_argument("--scenario", choices=SCENARIOS, default="normal")
    recover_parser.set_defaults(handler=_recover)

    resume_parser = subparsers.add_parser(
        "resume",
        help="Resume a paused (awaiting_user) task after a person resolved the blocking step",
    )
    resume_parser.add_argument("task_id")
    resume_parser.add_argument("--store", default="docubye-tasks.sqlite3", help="SQLite task store path")
    resume_parser.add_argument(
        "--note", required=True,
        help="Redacted human-resolution note recorded in the task history (no personal values)",
    )
    resume_parser.add_argument(
        "--confirm-human-resolution", action="store_true",
        help="Confirm a person resolved the blocking step; required to resume",
    )
    resume_parser.set_defaults(handler=_resume)

    # Backwards-compatible default: `docubye --scenario normal` still runs the demo.
    argv = sys.argv[1:]
    if not argv or argv[0] not in {"run", "recover", "resume", "-h", "--help"}:
        argv = ["run", *argv]
    args = parser.parse_args(argv)
    if args.command == "resume" and not args.confirm_human_resolution:
        parser.error("resume requires --confirm-human-resolution after a person resolved the blocking step")
    args.handler(args)


if __name__ == "__main__":
    main()
