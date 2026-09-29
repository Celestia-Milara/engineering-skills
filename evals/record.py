#!/usr/bin/env python3
"""Record a reviewed manual/model trace. This does not execute or automatically grade agents."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from prepare import digest, git, inventory


def final_inventory(run_directory, run):
    """Require the prepared workspace and its baseline, even for failure records."""
    expected_project = run_directory / "project"
    project = Path(run["project"]).resolve()
    if project != expected_project or expected_project.resolve() != expected_project or not project.is_dir():
        raise ValueError("Prepared project is missing, moved, or does not belong to this run/project")
    if not (project / ".git").exists() or Path(git(project, "rev-parse", "--show-toplevel")).resolve() != project:
        raise ValueError("Prepared project must have its own readable Git repository")
    baseline = run["baseline_commit"]
    if not isinstance(baseline, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", baseline):
        raise ValueError("Missing or invalid baseline commit identifier")
    if git(project, "cat-file", "-t", baseline) != "commit":
        raise ValueError("Prepared baseline commit is not readable")
    # HEAD may have changed: an unauthorized commit must still be recordable as a failed run.
    initial = run.get("initial_files")
    if not isinstance(initial, dict) or not initial or any(
        not isinstance(name, str) or not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
        for name, value in initial.items()
    ):
        raise ValueError("Initial file evidence is missing or invalid")
    snapshot = inventory(project)
    if not snapshot:
        raise ValueError("Final project file evidence is empty")
    return snapshot


def stage_bytes(directory, prefix, data):
    descriptor, name = tempfile.mkstemp(dir=directory, prefix=prefix, suffix=".tmp")
    path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="Prepared run directory")
    parser.add_argument("--trace", required=True, type=Path, help="Saved interaction/tool evidence; disclose gaps and score affected criteria not_observed")
    parser.add_argument("--model", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--loading-mode", required=True, choices=["native-discovery", "explicit-path", "catalog-injection"])
    parser.add_argument("--criterion", action="append", required=True, metavar="ID=pass|fail|not_observed")
    parser.add_argument("--notes", required=True, help="Short judgment with evidence locations; never an unsupported success claim")
    args = parser.parse_args()
    run_directory = args.run.resolve()
    run_path = run_directory / "run.json"
    lock = run_directory / ".record.lock"
    owns_lock = False
    staged_files = []
    try:
        # A concurrent recorder must not replace a result it did not read.
        with lock.open("x", encoding="utf-8") as stream:
            owns_lock = True
            stream.write(str(os.getpid()))
        run = json.loads(run_path.read_text(encoding="utf-8"))
        if run["status"] != "not_run":
            raise ValueError("This run already has a result; prepare a new run instead of replacing evidence")
        trace_data = args.trace.read_bytes()
        if not trace_data.strip():
            raise ValueError("A nonempty saved trace is required")
        if args.model == "unrecorded" or args.runtime == "unrecorded":
            raise ValueError("Record the actual model and runner")
        criteria = {}
        for value in args.criterion:
            name, separator, result = value.partition("=")
            if not separator or name not in run["criteria"] or result not in {"pass", "fail", "not_observed"} or name in criteria:
                raise ValueError(f"Invalid or duplicate criterion: {value}")
            criteria[name] = result
        if set(criteria) != set(run["criteria"]):
            raise ValueError("Explicitly score every criterion, including not_observed")
        snapshot = final_inventory(run_directory, run)
        trace = run_directory / "trace.txt"
        if trace.exists() and trace.read_bytes() != trace_data:
            raise ValueError("Existing trace.txt has different content; evidence will not be overwritten")
        run.update({"model": args.model, "runtime": args.runtime, "skill_loading_mode": args.loading_mode, "criteria": criteria,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "status": "fail" if "fail" in criteria.values() else "pass" if all(x == "pass" for x in criteria.values()) else "inconclusive",
                    "evidence": {"trace": "trace.txt", "trace_sha256": digest(trace_data), "review_method": "manual rubric assessment", "notes": args.notes},
                    "final_files": snapshot})
        staged_run = stage_bytes(run_directory, ".run-", (json.dumps(run, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        staged_files.append(staged_run)
        if not trace.exists():
            staged_trace = stage_bytes(run_directory, ".trace-", trace_data)
            staged_files.append(staged_trace)
            try:
                # Publishing a complete staged file with a hard link cannot overwrite evidence.
                os.link(staged_trace, trace)
            except FileExistsError:
                if trace.read_bytes() != trace_data:
                    raise ValueError("A conflicting trace.txt appeared; evidence will not be overwritten")
        os.replace(staged_run, run_path)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Recording failed: {exc}\n")
    finally:
        for path in staged_files:
            path.unlink(missing_ok=True)
        if owns_lock:
            lock.unlink(missing_ok=True)
    print(json.dumps({"status": run["status"], "run": str(run_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
