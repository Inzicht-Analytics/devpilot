"""Bounded, read-only runtime; no model credentials or mutation capability."""
import argparse
import json
import os
from .github_read import GitHubReadAdapter, GitHubItem, PILOT_REPOSITORY, GitHubReadError
from .orchestrator import create_task
from .planning import gather_snapshot, prepare_plan, PlanningDenied

MAX_TASKS = 5

class MockAdapter:
    repository = PILOT_REPOSITORY
    def list_issues(self):
        return (GitHubItem(1, "Example issue", "open", ""),)
    def list_pull_requests(self):
        return ()

def run(adapter, count=1):
    if type(count) is not int or not 1 <= count <= MAX_TASKS:
        raise ValueError("task count outside runtime budget")
    snapshot = gather_snapshot(adapter)
    results = []
    for _ in range(count):
        task, plan = prepare_plan(create_task(PILOT_REPOSITORY,
                                  "Review repository metadata"), snapshot)
        results.append({"task_id": str(task.id), "status": task.status.value,
                        "observations": plan.observations,
                        "proposed_steps": plan.proposed_steps,
                        "requires_approval": plan.requires_approval})
    return results

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-read", action="store_true")
    parser.add_argument("--count", type=int, default=1)
    args = parser.parse_args()
    try:
        adapter = GitHubReadAdapter(os.environ.get("DEVPILOT_READ_TOKEN", "")) if args.live_read else MockAdapter()
        results = run(adapter, args.count)
    except (ValueError, GitHubReadError, PlanningDenied):
        parser.exit(1, "Runtime rejected input or repository read failed.\n")
    print(json.dumps({"mode": "live-read" if args.live_read else "mock",
                      "results": results}))

if __name__ == "__main__":
    main()
