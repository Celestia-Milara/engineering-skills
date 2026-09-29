#!/usr/bin/env python3
"""Prepare an isolated fixture and evidence record; never invoke a model or grade it."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(directory):
    return {p.relative_to(directory).as_posix(): digest(p.read_bytes())
            for p in sorted(directory.rglob("*")) if p.is_file() and ".git" not in p.relative_to(directory).parts}


def git(project, *args):
    return subprocess.run(["git", "-c", "user.name=Skill Evaluation", "-c", "user.email=eval@example.invalid", *args],
                          cwd=project, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding="utf-8").stdout.strip()


def prepare(case_id, mode, output=None, model="unrecorded", runtime="unrecorded", loading_mode="unrecorded"):
    suite = json.loads((ROOT / "evals" / "scenarios.json").read_text(encoding="utf-8"))
    case = next((case for case in suite["cases"] if case["id"] == case_id), None)
    if case is None:
        raise ValueError(f"Unknown case: {case_id}")
    if mode not in {"baseline", "minimal", "full"}:
        raise ValueError(f"Unknown mode: {mode}")
    if output is None:
        output = Path(tempfile.mkdtemp(prefix=f"engineering-skills-{case_id}-{mode}-"))
    else:
        output = Path(output).resolve()
        if output.exists():
            raise ValueError("--output must not exist; existing evaluation runs are never overwritten")
        if output.is_relative_to(ROOT):
            raise ValueError("Evaluation output must be outside the source repository")
        output.mkdir(parents=True)
    project = output / "project"
    fixture = ROOT / "evals" / "fixtures" / case["fixture"]
    shutil.copytree(fixture / "base", project)
    (project / "AGENTS.md").write_text(
        "# Project notes\n\nUse the existing Python standard library where applicable. "
        "Run Python checks with `python -m unittest discover -v`. "
        "For HTML text-only edits, inspect the exact change. "
        "Preserve work outside the user request.\n", encoding="utf-8")
    (project / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    installed = []
    if mode == "minimal":
        installed = ["decision-notes", "implement-work"]
    elif mode == "full":
        installed = sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir())
    for name in installed:
        shutil.copytree(ROOT / "skills" / name, project / ".agents" / "skills" / name)
    git(project, "init", "--quiet")
    git(project, "add", ".")
    git(project, "commit", "--quiet", "-m", "Evaluation fixture baseline")
    baseline_commit = git(project, "rev-parse", "HEAD")
    if (fixture / "pending").is_dir():
        shutil.copytree(fixture / "pending", project, dirs_exist_ok=True)

    prompt = case["prompt"]
    explicit = case.get("explicit_skill")
    if explicit in installed:
        prompt = f"使用 ${explicit}（.agents/skills/{explicit}/SKILL.md）。\n\n" + prompt
    (output / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    # Rubric and scripted future turns stay outside the agent project to avoid answer leakage.
    (output / "rubric.json").write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    snapshot = inventory(project)
    run = {
        "format_version": 1, "status": "not_run", "scenario_id": case_id, "mode": mode,
        "prepared_at": datetime.now(timezone.utc).isoformat(), "project": str(project),
        "model": model, "runtime": runtime, "skill_loading_mode": loading_mode, "installed_skills": installed,
        "baseline_commit": baseline_commit, "starting_status": git(project, "status", "--short"),
        "fixture_sha256": digest(json.dumps(inventory(fixture), sort_keys=True).encode()),
        "scenario_sha256": digest(json.dumps(case, ensure_ascii=False, sort_keys=True).encode()),
        "skills_sha256": digest(json.dumps(inventory(ROOT / "skills"), sort_keys=True).encode()),
        "sources_manifest_sha256": digest((ROOT / "sources.json").read_bytes()),
        "initial_files": snapshot, "criteria": {item["id"]: "not_observed" for item in case["criteria"]},
        "evidence": None
    }
    (output / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", help="Scenario ID from scenarios.json")
    parser.add_argument("--mode", choices=["baseline", "minimal", "full"], default="full")
    parser.add_argument("--output", type=Path, help="New directory outside the source repository; default: OS temporary directory")
    parser.add_argument("--model", default="unrecorded", help="Exact model/version; must be set before recording a result")
    parser.add_argument("--runtime", default="unrecorded", help="Runner and version; must be set before recording a result")
    parser.add_argument("--loading-mode", choices=["native-discovery", "explicit-path", "catalog-injection", "unrecorded"], default="unrecorded")
    args = parser.parse_args()
    try:
        output = prepare(args.case, args.mode, args.output, args.model, args.runtime, args.loading_mode)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Preparation failed: {exc}\n")
    print(json.dumps({"run_directory": str(output), "project": str(output / "project"),
                      "prompt": str(output / "prompt.txt"), "status": "not_run"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
