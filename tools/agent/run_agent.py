"""Run agent scaffold: produce proposed changes (do NOT commit).

This script is intentionally minimal: it demonstrates how the autonomous agent
can produce filesystem changes in allowed directories without committing them.
The workflow (.github/workflows/agent-propose-changes.yml) will run this script
and later create a PR from the produced changes.

Behavior:
- Reads BRANCH_NAME from --branch-name or environment
- Reads ALLOWED_DIRS from environment (comma-separated)
- Writes a small proposal file under the first allowed directory (docs by default)
- Exits 0

Extend this script to implement planning, LLM calls, patch generation, etc.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Minimal agent that produces proposed changes (no commit)")
    p.add_argument("--branch-name", dest="branch_name", help="Target branch name for proposals", required=False)
    return p.parse_args()


def get_allowed_dirs() -> list[Path]:
    env = os.environ.get("ALLOWED_DIRS", "docs,src,tests")
    parts = [p.strip() for p in env.split(",") if p.strip()]
    return [Path(p) for p in parts]


def safe_write_proposal(target_dir: Path, branch_name: str) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"agent-proposal-{ts}.md"
    path = target_dir / filename
    content = f"# Agent proposal\n\n- branch: {branch_name}\n- timestamp: {ts}\n\nThis file is an automated placeholder proposal produced by tools/agent/run_agent.py.\nReplace this content with the agent's actual proposed changes (patch list, reasoning, etc.).\n"
    path.write_text(content, encoding="utf-8")
    return path


def main() -> int:
    args = parse_args()
    branch_name = args.branch_name or os.environ.get("BRANCH_NAME") or "auto/agent-local"

    allowed = get_allowed_dirs()
    if not allowed:
        print("No allowed directories configured; exiting.")
        return 0

    # Prefer docs, then src, then tests if present in allowed list
    preferred = None
    for choice in ("docs", "src", "tests"):
        for d in allowed:
            if d.name == choice:
                preferred = d
                break
        if preferred:
            break

    if not preferred:
        # fallback to first allowed dir path
        preferred = allowed[0]

    # Ensure the path is within repository workspace
    repo_root = Path.cwd()
    target_dir = repo_root / preferred

    try:
        written = safe_write_proposal(target_dir, branch_name)
        print(f"Wrote proposal: {written}")
        # Do NOT run git add/commit here; workflow will handle committing via create-pull-request
        return 0
    except Exception as e:
        print(f"Failed to write proposal: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
