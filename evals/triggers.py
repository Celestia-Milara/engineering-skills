#!/usr/bin/env python3
"""Prepare native-discovery prompts without exposing routing labels to the actor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from prepare import ROOT, prepare

SUITE = ROOT / "evals" / "triggers.json"


def load_suite():
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    skills = {p.name for p in (ROOT / "skills").iterdir() if p.is_dir()}
    seen = set()
    for case in suite["cases"]:
        if case["id"] in seen:
            raise ValueError(f"Duplicate trigger ID: {case['id']}")
        seen.add(case["id"])
        required = set(case["expected_skills"])
        allowed = set(case["allowed_skills"])
        forbidden = set(case["forbidden_skills"])
        if (required | allowed | forbidden) != skills or required & allowed or (required | allowed) & forbidden:
            raise ValueError(f"Invalid routing sets: {case['id']}")
        if "$" in case["prompt"] or "SKILL.md" in case["prompt"]:
            raise ValueError(f"Explicit invocation leaked into implicit test: {case['id']}")
    return suite


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", nargs="?", help="Omit to list the bilingual corpus")
    parser.add_argument("--mode", choices=["full"], default="full", help="Routing labels apply to this complete package only")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--host", choices=["codex", "claude"], default="codex")
    args = parser.parse_args()
    suite = load_suite()
    if args.case is None:
        print(json.dumps({"count": len(suite["cases"]), "cases": [
            {"id": c["id"], "language": c["language"], "expected_skills": c["expected_skills"]}
            for c in suite["cases"]]}, ensure_ascii=False, indent=2))
        return
    kwargs = {"suite_path": SUITE, "loading_mode": "native-discovery", "host": args.host}
    output = prepare(args.case, args.mode, args.output, **kwargs)
    print(json.dumps({"run_directory": str(output), "status": "not_run"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
