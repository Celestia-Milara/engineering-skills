#!/usr/bin/env python3
"""Read-only package checks. Source hashes describe Git blobs, not worktree bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

try:
    import yaml
except ImportError:
    yaml = None


SHA256 = re.compile(r"^[0-9a-f]{64}$")
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_KEYS = {"name", "description", "license", "compatibility", "allowed-tools", "metadata"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def local_markdown_links(text: str):
    """Yield (line, destination) for ordinary inline and reference Markdown links.

    Fenced code and inline code are excluded. HTML links are not interpreted.
    Balanced parentheses in an inline destination are supported.
    """
    visible = []
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^\s*(?:>\s*)?(`{3,}|~{3,})(.*)$", line)
        if marker:
            token, suffix = marker.groups()
            if fence is None:
                fence = (token[0], len(token))
            elif token[0] == fence[0] and len(token) >= fence[1] and not suffix.strip():
                fence = None
            continue
        if fence is None:
            visible.append((number, re.sub(r"(`+).*?\1", "", line)))

    definitions = {}
    for number, line in visible:
        definition = re.match(r"^\s{0,3}\[([^\]]+)\]:\s*(<[^>]+>|\S+)", line)
        if definition:
            label, target = definition.groups()
            definitions[label.strip().casefold()] = target.strip("<>")
            yield number, target.strip("<>")
    for number, line in visible:
        if re.match(r"^\s{0,3}\[[^\]]+\]:", line):
            continue
        for start in re.finditer(r"!?\[[^\]\n]*\]\(", line):
            cursor, depth = start.end(), 1
            end = cursor
            while end < len(line) and depth:
                if line[end] == "\\":
                    end += 2
                    continue
                if line[end] == "(":
                    depth += 1
                elif line[end] == ")":
                    depth -= 1
                end += 1
            if depth:
                continue
            target = line[cursor:end - 1].strip()
            if target.startswith("<") and ">" in target:
                target = target[1:target.index(">")]
            else:
                target = target.split()[0] if target else ""
            if target:
                yield number, target
        for reference in re.finditer(r"\[([^\]]+)\]\[([^\]]*)\]", line):
            label = (reference[2] or reference[1]).strip().casefold()
            if label in definitions:
                # The definition was already checked above.
                continue
            yield number, "!undefined-reference:" + label


def validate(root: Path, selected: set[str] | None = None,
             source_roots: dict[str, Path] | None = None) -> dict:
    root = root.resolve()
    issues = []
    counts = {"skills": 0, "markdown_files": 0, "local_links": 0,
              "distributed_hashes": 0, "source_blobs": 0, "licenses": 0}

    def error(code, path, message):
        issues.append({"code": code, "path": str(path), "message": message})

    def package_path(value, context):
        if not isinstance(value, str) or not value:
            error("manifest.path", context, "Expected a nonempty relative POSIX path")
            return None
        parsed = PurePosixPath(value)
        if parsed.is_absolute() or ".." in parsed.parts or "\\" in value or ":" in value:
            error("manifest.path", context, f"Unsafe package/source path: {value}")
            return None
        return root.joinpath(*parsed.parts)

    manifest_path = root / "sources.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        error("manifest.read", "sources.json", str(exc))
        return {"ok": False, "root": str(root), "counts": counts, "issues": issues}
    if not isinstance(manifest, dict) or manifest.get("format_version") != 2:
        error("manifest.version", "sources.json", "Expected format_version: 2")
        return {"ok": False, "root": str(root), "counts": counts, "issues": issues}

    sections = {}
    for key in ("sources", "licenses", "skill_sources", "skill_dependencies"):
        value = manifest.get(key)
        if not isinstance(value, dict):
            error("manifest.schema", key, "Expected an object")
            value = {}
        sections[key] = value
    sources = sections["sources"]
    for name, source in sources.items():
        if not isinstance(source, dict) or not re.fullmatch(r"[0-9a-f]{40,64}", str(source.get("commit", ""))):
            error("manifest.source", name, "Source requires a full commit SHA")
        if not isinstance(source, dict) or not isinstance(source.get("origin"), str) or not source["origin"]:
            error("manifest.source", name, "Source requires a nonempty origin")

    all_skills = {p.name: p for p in (root / "skills").iterdir() if p.is_dir()} if (root / "skills").is_dir() else {}
    if not all_skills:
        error("skill.missing", "skills", "No skill directories found")
    for key in ("skill_sources", "skill_dependencies"):
        missing = set(all_skills) - set(sections[key])
        unknown = set(sections[key]) - set(all_skills)
        if missing or unknown:
            error("manifest.inventory", key, f"Missing skills: {sorted(missing)}; unknown skills: {sorted(unknown)}")
    selected = set(all_skills) if selected is None else selected
    unknown = selected - set(all_skills)
    if unknown:
        error("skill.selection", "--skills", f"Unknown skills: {sorted(unknown)}")
    selected &= set(all_skills)
    dependencies = dict(sections["skill_dependencies"])
    for skill, required in dependencies.items():
        if not isinstance(required, list) or any(not isinstance(x, str) for x in required):
            error("manifest.dependencies", skill, "Expected an array of skill names")
            dependencies[skill] = []
            continue
        if len(required) != len(set(required)) or skill in required or set(required) - set(all_skills):
            error("manifest.dependencies", skill, "Dependencies must be unique, known, and exclude self")
        if skill in selected:
            for name in required:
                if name not in selected:
                    error("dependency.missing", skill, f"Required skill not selected: {name}")

    if yaml is None:
        error("environment.pyyaml", "scripts/requirements.txt", "Install validation dependencies: python -m pip install -r scripts/requirements.txt")
    descriptions = {}
    for name in sorted(selected):
        path = all_skills[name] / "SKILL.md"
        counts["skills"] += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            error("skill.read", path.relative_to(root), str(exc))
            continue
        match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
        if not match:
            error("skill.frontmatter", path.relative_to(root), "Missing or malformed YAML frontmatter")
            continue
        if yaml is None:
            continue
        try:
            metadata = yaml.safe_load(match[1])
        except yaml.YAMLError as exc:
            error("skill.frontmatter", path.relative_to(root), str(exc))
            continue
        if not isinstance(metadata, dict):
            error("skill.frontmatter", path.relative_to(root), "Frontmatter must be an object")
            continue
        unexpected = set(metadata) - FRONTMATTER_KEYS
        if unexpected:
            error("skill.frontmatter", path.relative_to(root), f"Unsupported fields: {sorted(unexpected)}")
        actual_name = metadata.get("name")
        if not isinstance(actual_name, str) or not SKILL_NAME.fullmatch(actual_name) or len(actual_name) > 64 or actual_name != name:
            error("skill.name", path.relative_to(root), "name must match its directory and use lower-case hyphen naming, at most 64 characters")
        description = metadata.get("description")
        if not isinstance(description, str) or not description.strip() or len(description) > 1024 or "<" in description or ">" in description:
            error("skill.description", path.relative_to(root), "description must be a nonempty string, at most 1024 characters, without angle brackets")
        else:
            descriptions[name] = len(description)

    markdown = list(root.rglob("*.md")) if selected == set(all_skills) else [p for n in selected for p in all_skills[n].rglob("*.md")]
    for path in sorted(markdown):
        # Ignore hidden runtime environments and generated reports outside package sources.
        if any(part in {".git", ".venv", "node_modules", "__pycache__"} for part in path.relative_to(root).parts):
            continue
        counts["markdown_files"] += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            error("markdown.read", path.relative_to(root), str(exc))
            continue
        for line, target in local_markdown_links(text):
            location = f"{path.relative_to(root).as_posix()}:{line}"
            if target.startswith("!undefined-reference:"):
                error("link.reference", location, target.removeprefix("!undefined-reference:"))
                continue
            try:
                parsed = urlsplit(target)
            except ValueError as exc:
                error("link.invalid", location, str(exc))
                continue
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            counts["local_links"] += 1
            destination = (path.parent / unquote(parsed.path)).resolve()
            if not destination.exists():
                error("link.missing", location, target)
                continue
            try:
                relative = destination.relative_to(root / "skills")
            except ValueError:
                continue
            if relative.parts and relative.parts[0] not in selected:
                error("dependency.link", location, f"Link requires unselected skill: {relative.parts[0]}")
            if path.is_relative_to(root / "skills"):
                owner = path.relative_to(root / "skills").parts[0]
                dependency = relative.parts[0]
                if dependency != owner and dependency not in dependencies.get(owner, []):
                    error("dependency.undeclared", location, f"Cross-skill link requires declaration: {dependency}")

    entries = manifest.get("files")
    if not isinstance(entries, list):
        error("manifest.files", "files", "Expected an array")
        entries = []
    destinations = set()
    source_roots = source_roots or {}
    for key in set(source_roots) - set(sources):
        error("source.root", key, "Unknown source name")
    for index, entry in enumerate(entries):
        context = f"files[{index}]"
        if not isinstance(entry, dict):
            error("manifest.file", context, "Expected an object")
            continue
        destination = entry.get("destination")
        path = package_path(destination, context)
        if path is None:
            continue
        if destination in destinations:
            error("manifest.duplicate", context, destination)
        destinations.add(destination)
        treatment = entry.get("treatment")
        if treatment not in {"verbatim", "translated", "adapted", "original"}:
            error("manifest.treatment", context, "Expected verbatim, translated, adapted, or original")
        expected = entry.get("distributed_sha256", "")
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            error("manifest.hash", context, "Invalid distributed_sha256")
        try:
            data = path.read_bytes()
            counts["distributed_hashes"] += 1
            if sha256(data) != expected:
                error("hash.distributed", destination, f"Expected {expected}; actual {sha256(data)}")
        except OSError as exc:
            data = None
            error("manifest.destination", destination, str(exc))
        references = entry.get("source_files")
        if treatment == "original":
            if references != []:
                error("manifest.original", context, "Original files require an empty source_files array; do not invent upstream provenance")
            continue
        if not isinstance(references, list) or not references:
            error("manifest.source_files", context, "Expected a nonempty source_files array")
            continue
        if treatment == "verbatim" and len(references) != 1:
            error("manifest.verbatim", context, "Verbatim files require exactly one source")
        for reference in references:
            if not isinstance(reference, dict):
                error("manifest.source_file", context, "Expected an object")
                continue
            source, source_path, expected_source = (reference.get(k) for k in ("source", "path", "sha256"))
            if not isinstance(source, str) or source not in sources:
                error("manifest.source_file", context, "Unknown source")
                continue
            if package_path(source_path, context) is None:
                continue
            if not isinstance(expected_source, str) or not SHA256.fullmatch(expected_source):
                error("manifest.hash", context, "Invalid source sha256")
                continue
            if treatment == "verbatim" and expected_source != expected:
                error("manifest.verbatim", destination, "Verbatim source and distribution hashes differ")
            if source in source_roots:
                commit = sources[source].get("commit", "") if isinstance(sources[source], dict) else ""
                try:
                    result = subprocess.run(["git", "show", f"{commit}:{source_path}"], cwd=source_roots[source],
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                    counts["source_blobs"] += 1
                    actual_source = sha256(result.stdout)
                    if actual_source != expected_source:
                        error("hash.source", f"{source}:{source_path}", f"Expected {expected_source}; commit blob has {actual_source}")
                except (OSError, subprocess.CalledProcessError) as exc:
                    error("source.read", f"{source}:{source_path}", str(exc))
    for name in selected:
        expected_path = f"skills/{name}/SKILL.md"
        if expected_path not in destinations:
            error("manifest.coverage", expected_path, "Skill entrypoint has no provenance record")

    for name in sorted(selected):
        source = sections["skill_sources"].get(name)
        archive = sections["licenses"].get(source) if isinstance(source, str) else None
        if not isinstance(source, str) or (source != "original" and source not in sources) or archive is None:
            error("license.source", name, "Missing source/license mapping")
            continue
        entrypoint = next((entry for entry in entries if isinstance(entry, dict)
                           and entry.get("destination") == f"skills/{name}/SKILL.md"), None)
        if entrypoint and (entrypoint.get("treatment") == "original") != (source == "original"):
            error("manifest.original", name, "Original skill mapping and entrypoint treatment must agree")
        archive_path = package_path(archive, f"licenses.{source}")
        if archive_path is None:
            continue
        try:
            expected_license = archive_path.read_bytes()
            actual_license = (all_skills[name] / "LICENSE").read_bytes()
            counts["licenses"] += 1
            if not expected_license.strip() or actual_license != expected_license:
                error("license.content", name, "Skill LICENSE must match its nonempty archived source license")
        except OSError as exc:
            error("license.read", name, str(exc))

    return {"ok": not issues, "root": str(root), "selected_skills": sorted(selected),
            "counts": counts, "description_lengths": descriptions, "issues": issues,
            "source_verification": "commit blobs checked for supplied roots" if source_roots else "not requested; distributed files and manifest checked"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--skills", help="Comma-separated installed selection; required dependencies must be included")
    parser.add_argument("--source-root", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--json", action="store_true", help="Write one JSON report to stdout")
    args = parser.parse_args(argv)
    roots = {}
    for value in args.source_root:
        name, separator, path = value.partition("=")
        if not separator or not name or not path:
            parser.error("--source-root must have the form NAME=PATH")
        roots[name] = Path(path)
    selected = {x.strip() for x in args.skills.split(",") if x.strip()} if args.skills is not None else None
    report = validate(args.root, selected, roots)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("PASS" if report["ok"] else "FAIL", json.dumps(report["counts"], ensure_ascii=False))
        for issue in report["issues"]:
            print(f"{issue['code']}: {issue['path']}: {issue['message']}")
        print(report["source_verification"] if "source_verification" in report else "Manifest validation failed")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
