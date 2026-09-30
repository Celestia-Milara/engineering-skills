#!/usr/bin/env python3
"""Prepare an isolated fixture and evidence record; never invoke a model or grade it."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
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
                          text=True, encoding="utf-8").stdout.rstrip("\r\n")


def upstream_skills(project, source_root, skill_directory=".agents/skills"):
    """Export pinned Git blobs, including the two root skills' documented dependencies."""
    manifest = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    source = manifest["sources"]["mattpocock"]
    commit = source["commit"]
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
        raise ValueError("Invalid pinned upstream commit")
    source_root = Path(source_root or ROOT.parent / "mattpocock_skills").resolve()
    roots = ["implement", "tdd"]
    dependencies = ["code-review", "codebase-design"]
    names = roots + dependencies
    exported = {}
    for name in names:
        prefix = f"skills/engineering/{name}/"
        listed = subprocess.run(["git", "ls-tree", "-r", "-z", commit, "--", prefix], cwd=source_root,
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
        entries = [entry for entry in listed.split(b"\0") if entry]
        if not entries:
            raise ValueError(f"Pinned upstream skill is missing: {name}")
        for entry in entries:
            metadata, path_bytes = entry.split(b"\t", 1)
            mode, kind, _ = metadata.split(b" ", 2)
            path = path_bytes.decode("utf-8")
            relative = PurePosixPath(path.removeprefix(prefix))
            if (mode not in {b"100644", b"100755"} or kind != b"blob" or not path.startswith(prefix)
                    or relative.is_absolute() or ".." in relative.parts or "\\" in path or ":" in path):
                raise ValueError(f"Unsafe upstream blob: {path}")
            data = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=source_root, check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
            target = project / skill_directory / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            exported[path] = digest(data)
    license_data = subprocess.run(["git", "show", f"{commit}:LICENSE"], cwd=source_root, check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    (project / skill_directory / "UPSTREAM.LICENSE").write_bytes(license_data)
    exported["LICENSE"] = digest(license_data)
    # Verify every blob already covered by the source manifest; additional upstream dependencies
    # are identified by the immutable commit and their exported hashes.
    for item in manifest["files"]:
        for original in item.get("source_files", []):
            path = original["path"]
            if original["source"] == "mattpocock" and path in exported and exported[path] != original["sha256"]:
                raise ValueError(f"Pinned upstream source hash mismatch: {path}")
    return names, {"source": "mattpocock", "commit": commit, "origin": source["origin"],
                   "roots": roots, "dependencies": dependencies, "exported_blobs": exported,
                   "limitations": ["Upstream slash commands and user-only invocation depend on the host.",
                                   "code-review also refers to project issue-tracker setup; this fixture does not run setup."]}


def prepare(case_id, mode, output=None, model="unrecorded", runtime="unrecorded", loading_mode="unrecorded",
            suite_path=None, upstream_source=None, host="codex"):
    suite_path = Path(suite_path or ROOT / "evals" / "scenarios.json").resolve()
    if not suite_path.is_relative_to((ROOT / "evals").resolve()) or suite_path.suffix != ".json":
        raise ValueError("Suite must be a JSON file inside evals/")
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    if not isinstance(suite.get("cases"), list):
        raise ValueError("Suite must define a cases array")
    case = next((case for case in suite["cases"] if case["id"] == case_id), None)
    if case is None:
        raise ValueError(f"Unknown case: {case_id}")
    case = dict(case)
    if "criteria" not in case:
        case["criteria"] = suite.get("criteria")
    if mode not in {"baseline", "upstream", "minimal", "full"}:
        raise ValueError(f"Unknown mode: {mode}")
    if suite.get("allowed_modes") is not None and mode not in suite["allowed_modes"]:
        raise ValueError(f"Suite does not define expectations for mode: {mode}")
    if host not in {"codex", "claude"}:
        raise ValueError(f"Unknown host: {host}")
    skill_directory = ".claude/skills" if host == "claude" else ".agents/skills"
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
    fixture_name = case["fixture"]
    if (not isinstance(fixture_name, str) or not re.fullmatch(r"[a-z0-9-]+", fixture_name)
            or not isinstance(case.get("prompt"), str) or not isinstance(case.get("criteria"), list)):
        raise ValueError("Invalid fixture, prompt, or criteria in suite case")
    fixture = ROOT / "evals" / "fixtures" / fixture_name
    shutil.copytree(fixture / "base", project)
    (project / "AGENTS.md").write_text(
        "# Project notes\n\nUse the existing Python standard library where applicable. "
        "Run Python checks with `python -m unittest discover -v`. "
        "For HTML text-only edits, inspect the exact change. "
        "Preserve work outside the user request.\n", encoding="utf-8")
    if host == "claude":
        shutil.copyfile(project / "AGENTS.md", project / "CLAUDE.md")
    (project / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    installed = []
    if mode == "minimal":
        installed = ["decision-notes", "implement-work"]
    elif mode == "full":
        installed = sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir())
    upstream = None
    if mode == "upstream":
        installed, upstream = upstream_skills(project, upstream_source, skill_directory)
    else:
        for name in installed:
            shutil.copytree(ROOT / "skills" / name, project / skill_directory / name)
    git(project, "init", "--quiet")
    git(project, "add", ".")
    git(project, "commit", "--quiet", "-m", "Evaluation fixture baseline")
    baseline_commit = git(project, "rev-parse", "HEAD")
    if (fixture / "pending").is_dir():
        shutil.copytree(fixture / "pending", project, dirs_exist_ok=True)
    staged_paths = case.get("staged_paths", [])
    if not isinstance(staged_paths, list) or any(not isinstance(value, str) for value in staged_paths):
        raise ValueError("staged_paths must be an array of relative file paths")
    for value in staged_paths:
        parsed = PurePosixPath(value)
        if (not value or parsed.is_absolute() or ".." in parsed.parts or "\\" in value or ":" in value
                or not (project / value).resolve().is_relative_to(project.resolve())):
            raise ValueError(f"Unsafe staged fixture path: {value}")
    if staged_paths:
        git(project, "add", "--", *staged_paths)
        # Synthetic identity is confined to this disposable repository, never global config.
        git(project, "config", "user.name", "Skill Evaluation")
        git(project, "config", "user.email", "eval@example.invalid")

    prompt = case["prompt"]
    explicit = case.get("explicit_skill")
    prompt_explicit_skill = None
    if mode == "upstream" and explicit == "implement-work":
        prompt = f"使用 $implement（{skill_directory}/implement/SKILL.md）。\n\n" + prompt
        prompt_explicit_skill = "implement"
    elif explicit in installed:
        prompt = f"使用 ${explicit}（{skill_directory}/{explicit}/SKILL.md）。\n\n" + prompt
        prompt_explicit_skill = explicit
    (output / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    # Rubric and scripted future turns stay outside the agent project to avoid answer leakage.
    (output / "rubric.json").write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    snapshot = inventory(project)
    run = {
        "format_version": 1, "status": "not_run", "scenario_id": case_id, "mode": mode,
        "prepared_at": datetime.now(timezone.utc).isoformat(), "project": str(project),
        "model": model, "runtime": runtime, "skill_loading_mode": loading_mode, "installed_skills": installed,
        "baseline_commit": baseline_commit, "starting_status": git(project, "status", "--short"),
        "starting_index_sha256": digest(git(project, "ls-files", "--stage").encode()),
        "starting_tracked_diff_sha256": digest(git(project, "diff", "HEAD", "--").encode()),
        "fixture_sha256": digest(json.dumps(inventory(fixture), sort_keys=True).encode()),
        "scenario_sha256": digest(json.dumps(case, ensure_ascii=False, sort_keys=True).encode()),
        "prepared_prompt_sha256": digest((output / "prompt.txt").read_bytes()),
        "rubric_sha256": digest((output / "rubric.json").read_bytes()),
        "skills_sha256": digest(json.dumps(inventory(ROOT / "skills"), sort_keys=True).encode()),
        "sources_manifest_sha256": digest((ROOT / "sources.json").read_bytes()),
        "suite": suite_path.relative_to(ROOT).as_posix(), "host": host, "skill_directory": skill_directory,
        "selection": case.get("selection", "unrecorded"), "prompt_explicit_skill": prompt_explicit_skill,
        "installed_skills_sha256": digest(json.dumps(inventory(project / skill_directory), sort_keys=True).encode()),
        "upstream": upstream,
        "initial_files": snapshot, "criteria": {item["id"]: "not_observed" for item in case["criteria"]},
        "evidence": None
    }
    (output / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", help="Scenario ID from scenarios.json")
    parser.add_argument("--mode", choices=["baseline", "upstream", "minimal", "full"], default="full")
    parser.add_argument("--suite", type=Path, help="Suite JSON inside evals/; default: scenarios.json")
    parser.add_argument("--upstream-source", type=Path, help="Local upstream Git repository; exports sources.json's pinned commit")
    parser.add_argument("--host", choices=["codex", "claude"], default="codex", help="Choose the host's native project skill directory")
    parser.add_argument("--output", type=Path, help="New directory outside the source repository; default: OS temporary directory")
    parser.add_argument("--model", default="unrecorded", help="Exact model/version; must be set before recording a result")
    parser.add_argument("--runtime", default="unrecorded", help="Runner and version; must be set before recording a result")
    parser.add_argument("--loading-mode", choices=["native-discovery", "explicit-path", "catalog-injection", "unrecorded"], default="unrecorded")
    args = parser.parse_args()
    try:
        output = prepare(args.case, args.mode, args.output, args.model, args.runtime, args.loading_mode,
                         args.suite, args.upstream_source, args.host)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Preparation failed: {exc}\n")
    print(json.dumps({"run_directory": str(output), "project": str(output / "project"),
                      "prompt": str(output / "prompt.txt"), "status": "not_run"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
