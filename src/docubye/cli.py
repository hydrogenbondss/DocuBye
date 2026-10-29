"""Command-line demo for DocuBye's synthetic workflow."""

from __future__ import annotations

import argparse
import json

from .agent import MockRemovalAgent, ReviewSummary
from .mock_site import running_mock_site
from .models import SyntheticProfile
from .planner import OpenAIFieldPlanner, RuleBasedPlanner


def _approval_prompt(review: ReviewSummary) -> bool | None:
    print("\nSubmission review")
    print(f"Destination: {review.destination}")
    print("Data categories: " + ", ".join(review.data_categories))
    print("Profile values are synthetic and remain inside the local fixture.")
    answer = input("Submit this synthetic request? Type 'yes' to approve: ").strip().casefold()
    return answer == "yes"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DocuBye's local synthetic removal demo")
    parser.add_argument("--scenario", choices=["normal", "challenge", "unexpected", "verified", "early-submit"], default="normal")
    parser.add_argument("--planner", choices=["rules", "openai"], default="rules")
    parser.add_argument("--headed", action="store_true", help="Show the local browser window")
    args = parser.parse_args()

    planner = OpenAIFieldPlanner() if args.planner == "openai" else RuleBasedPlanner()
    with running_mock_site(args.scenario) as (base_url, state):
        print(f"DocuBye mock site: {base_url}")
        print("Local synthetic data only. No real removal site will be contacted.")
        result = MockRemovalAgent(planner=planner, headless=not args.headed).run(
            base_url=base_url,
            profile=SyntheticProfile(),
            approval_callback=_approval_prompt,
        )
        print("\nResult: " + result.message)
        print(json.dumps(result.task.to_public_dict(), indent=2))
        print(f"Synthetic fixture submissions: {state.submission_count}")
        if result.blocked_hosts:
            print("Blocked external hosts: " + ", ".join(sorted(set(result.blocked_hosts))))
        print(f"Pre-approval submissions blocked: {result.blocked_submission_attempts}")


if __name__ == "__main__":
    main()
