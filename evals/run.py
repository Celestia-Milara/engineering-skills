#!/usr/bin/env python3
"""Run one prepared prompt in a headless host; save raw evidence, never grade it."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid

from prepare import ROOT, digest, git, inventory
from record import final_inventory


def now():
    return datetime.now(timezone.utc).isoformat()


def executable_path(host, supplied=None):
    """Use a native executable, never a shell/npm batch shim."""
    candidate = supplied or shutil.which(host)
    if candidate is None:
        raise ValueError(f"{host} executable not found; provide --executable")
    path = Path(candidate).resolve()
    if path.suffix.lower() in {".cmd", ".bat", ".ps1"}:
        npm = path.parent / "node_modules"
        if host == "claude":
            candidates = [npm / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"]
        else:
            candidates = sorted((npm / "@openai" / "codex" / "node_modules").glob(
                "@openai/codex-win32-*/vendor/*/bin/codex.exe"))
        candidates = [item for item in candidates if item.is_file()]
        if len(candidates) != 1:
            raise ValueError("Cannot resolve npm shim to a single native executable; provide --executable")
        path = candidates[0].resolve()
    if not path.is_file():
        raise ValueError("--executable must be an existing native executable")
    return path


def probe(executable, args, directory, artifact):
    result = subprocess.run([str(executable), *args], cwd=directory, shell=False,
                            capture_output=True, timeout=15)
    (artifact / ("version.stdout" if args == ["--version"] else "help.stdout")).write_bytes(result.stdout)
    (artifact / ("version.stderr" if args == ["--version"] else "help.stderr")).write_bytes(result.stderr)
    if result.returncode:
        raise ValueError(f"Host {' '.join(args)} exited {result.returncode}; see captured stderr")
    return result.stdout.decode("utf-8", errors="replace")


def global_inputs(host):
    """Hash known nonsecret runtime inputs; do not export configuration or credentials."""
    user_directory = Path.home()
    codex_directory = Path(os.environ.get("CODEX_HOME", str(user_directory / ".codex")))
    claude_directory = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(user_directory / ".claude")))
    locations = ([codex_directory / "skills", user_directory / ".agents" / "skills",
                  codex_directory / "config.toml", codex_directory / "AGENTS.md"] if host == "codex"
                 else [claude_directory / "skills", claude_directory / "settings.json",
                       claude_directory / "CLAUDE.md", user_directory / ".claude.json"])
    observed = []
    for path in locations:
        entry = {"path": str(path), "exists": path.exists()}
        try:
            if path.is_file():
                entry["sha256"] = digest(path.read_bytes())
            elif path.is_dir():
                files = inventory(path)
                entry.update({"file_count": len(files), "inventory_sha256": digest(
                    json.dumps(files, sort_keys=True).encode())})
        except OSError as exc:
            entry["error"] = type(exc).__name__
        observed.append(entry)
    return observed


def host_argv(host, executable, project, model, session_id=None, sandbox="workspace-write", windows_sandbox=None):
    if host == "codex":
        argv = [str(executable), "exec", "--json", "--color", "never", "--ignore-user-config",
                "--sandbox", sandbox, "--model", model, "-C", str(project)]
        if windows_sandbox is not None:
            argv.extend(["-c", f'windows.sandbox="{windows_sandbox}"'])
        return [*argv, "-"]
    return [str(executable), "-p", "--output-format", "stream-json", "--verbose",
            "--forward-subagent-text", "--include-hook-events", "--permission-prompts", "none",
            "--permission-mode", "acceptEdits", "--setting-sources", "project",
            "--session-id", session_id, "--model", model]


def stop_process(process):
    # Only terminate the process tree created by this invocation. No unrelated PID is accepted.
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], shell=False,
                       capture_output=True, timeout=15)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=5)


def launch_process(argv, project, stdout, stderr):
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    return subprocess.Popen(argv, cwd=project, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                            shell=False, **options)


def parse_json_lines(data):
    events, errors = [], []
    for number, line in enumerate(data.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("event is not an object")
            events.append(event)
        except (ValueError, UnicodeError) as exc:
            errors.append({"line": number, "error": str(exc)})
    return events, errors


def json_lines(path):
    return parse_json_lines(path.read_bytes())


def session_root(host):
    if host == "codex":
        return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "sessions"
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))) / "projects"


def copy_session(host, identifier, project, artifact, sessions=None):
    """Locate by the observed ID, then verify ID and working directory before copying."""
    root = Path(sessions or session_root(host)).resolve()
    if (not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", identifier)
            or not root.is_dir()):
        return None, "Host session ID or session directory unavailable"
    pattern = f"*{identifier}.jsonl" if host == "codex" else f"{identifier}.jsonl"
    candidates = []
    for source in root.rglob(pattern):
        resolved = source.resolve()
        if not resolved.is_relative_to(root):
            continue
        try:
            data = resolved.read_bytes()
            events, errors = parse_json_lines(data)
            if host == "codex":
                meta = next((event.get("payload", {}) for event in events if event.get("type") == "session_meta"), {})
                identity = (isinstance(meta, dict) and meta.get("id") == identifier and
                            isinstance(meta.get("cwd"), str) and Path(meta["cwd"]).resolve() == project)
            else:
                identity = any(event.get("sessionId") == identifier and isinstance(event.get("cwd"), str) and
                               Path(event["cwd"]).resolve() == project for event in events)
            if identity:
                candidates.append((resolved, data, events, errors))
        except (OSError, ValueError):
            continue
    if len(candidates) != 1:
        return None, f"Expected one session matching ID and cwd; found {len(candidates)}"
    source, data, events, errors = candidates[0]
    target = artifact / "session.jsonl"
    target.write_bytes(data)
    tool_calls = [event for event in events if event.get("type") == "response_item" and isinstance(event.get("payload"), dict) and
                  event.get("payload", {}).get("type") in {"function_call", "custom_tool_call"}]
    tool_results = [event for event in events if event.get("type") == "response_item" and isinstance(event.get("payload"), dict) and
                    event.get("payload", {}).get("type") in {"function_call_output", "custom_tool_call_output"}]
    return {"path": "session.jsonl", "source": str(source), "sha256": digest(target.read_bytes()),
            "event_count": len(events), "parse_errors": errors,
            "codex_tool_calls": len(tool_calls), "codex_tool_results": len(tool_results)}, None


def configuration_comparison(requested, models, contexts):
    """Compare requested values only with values explicitly present in raw host events."""
    field_values = {"model": models, "sandbox": [], "windows_sandbox": [],
                    "approval_policy": [], "reasoning_effort": []}
    for context in contexts:
        policy = context.get("sandbox_policy")
        if isinstance(policy, dict) and isinstance(policy.get("type"), str):
            mode = policy["type"]
            mode = {"readOnly": "read-only", "read_only": "read-only", "workspaceWrite": "workspace-write",
                    "workspace_write": "workspace-write"}.get(mode, mode)
            field_values["sandbox"].append(mode)
        for field in ("windows_sandbox", "approval_policy", "reasoning_effort"):
            if isinstance(context.get(field), str):
                field_values[field].append(context[field])
    assessments = {}
    for field, values in field_values.items():
        expected = requested.get(field)
        observed = sorted(set(values))
        status = ("not_requested" if expected is None else "not_observed" if not observed
                  else "match" if all(value == expected for value in observed) else "mismatch")
        assessments[field] = {"requested": expected, "observed": observed, "status": status}
    statuses = {entry["status"] for entry in assessments.values()}
    status = "mismatch" if "mismatch" in statuses else "not_observed" if "not_observed" in statuses else "observed_match"
    return {"status": status, "fields": assessments, "mismatch_observed": "mismatch" in statuses,
            "requires_manual_review": True,
            "notes": ["Requested flags do not prove effective permissions or reasoning configuration.",
                      "Windows sandbox implementation cannot be inferred from sandbox_policy.type.",
                      "Matching recorded values is not proof that two runs are comparable."]}


def summarize(host, stdout, session, artifact, requested_configuration=None):
    """Extract observable counters without turning availability into a completeness claim."""
    events, errors = json_lines(stdout)
    session_events = json_lines(artifact / "session.jsonl")[0] if session else []
    observed_types = sorted({str(event.get("type", "")) for event in events})
    usage = []
    tools = []
    actual_models = set()
    runtime_contexts = []
    identifiers = []
    for event in events:
        if event.get("type") == "thread.started" and event.get("thread_id"):
            identifiers.append(event["thread_id"])
        if event.get("session_id"):
            identifiers.append(event["session_id"])
        if isinstance(event.get("usage"), dict):
            usage.append({"source": "stdout", "type": event.get("type"), "usage": event["usage"]})
        item = event.get("item", {})
        if isinstance(item, dict) and item.get("type") in {"command_execution", "mcp_tool_call", "file_change"}:
            tools.append({"source": "stdout", "type": item["type"], "id": item.get("id")})
        message = event.get("message", {})
        if isinstance(message, dict):
            if message.get("model"):
                actual_models.add(message["model"])
            if isinstance(message.get("usage"), dict):
                usage.append({"source": "stdout.message", "type": event.get("type"), "usage": message["usage"]})
            for block in message.get("content", []) if isinstance(message.get("content"), list) else []:
                if isinstance(block, dict) and block.get("type") in {"tool_use", "tool_result"}:
                    tools.append({"source": "stdout.message", "type": block["type"], "id": block.get("id", block.get("tool_use_id"))})
    for index, event in enumerate(session_events, 1):
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            continue
        if event.get("type") == "turn_context":
            if isinstance(payload.get("model"), str):
                actual_models.add(payload["model"])
            context = {"source": "session.jsonl", "event_index": index, "timestamp": event.get("timestamp"),
                       "turn_id": payload.get("turn_id"), "model": payload.get("model")}
            for field in ("sandbox_policy", "permission_profile", "approval_policy", "windows_sandbox"):
                if field in payload:
                    context[field] = payload[field]
            # These are observed host fields, never defaults reconstructed from argv/config.
            if "effort" in payload or "reasoning_effort" in payload:
                context["reasoning_effort"] = payload.get("reasoning_effort", payload.get("effort"))
            else:
                collaboration = payload.get("collaboration_mode")
                settings = collaboration.get("settings") if isinstance(collaboration, dict) else None
                if isinstance(settings, dict) and "reasoning_effort" in settings:
                    context["reasoning_effort"] = settings["reasoning_effort"]
                    context["reasoning_effort_source"] = "collaboration_mode.settings.reasoning_effort"
            runtime_contexts.append(context)
        if event.get("type") == "event_msg" and payload.get("type") == "token_count":
            usage.append({"source": "session", "type": "token_count", "info": payload.get("info")})
        if event.get("type") == "response_item" and payload.get("type") in {
                "function_call", "custom_tool_call", "function_call_output", "custom_tool_call_output"}:
            tools.append({"source": "session", "type": payload["type"], "id": payload.get("call_id")})
    comparison = configuration_comparison(requested_configuration or {}, sorted(actual_models), runtime_contexts)
    policies = {json.dumps(context["sandbox_policy"], sort_keys=True) for context in runtime_contexts if "sandbox_policy" in context}
    return {"stdout_event_count": len(events), "stdout_event_types": observed_types,
            "stdout_parse_errors": errors, "observed_session_ids": sorted(set(identifiers)),
            "actual_models": sorted(actual_models), "usage_events": usage, "tool_events": tools,
            "runtime_contexts": runtime_contexts,
            "actual_sandbox_policies": [json.loads(policy) for policy in sorted(policies)],
            "actual_approval_policies": comparison["fields"]["approval_policy"]["observed"],
            "actual_reasoning_efforts": comparison["fields"]["reasoning_effort"]["observed"],
            "configuration_comparison": comparison,
            "tool_evidence_observed": bool(tools), "completeness": "requires_manual_review",
            "notes": ["Event presence is not proof of complete authorization ordering or read-only behavior.",
                      "Usage counters may overlap; do not sum incremental, cumulative, or repeated events.",
                      "Session formats are host internals and may change."]}


def execute(run_directory, host, model, loading_mode="native-discovery", executable=None, timeout=300,
            sessions=None, sandbox="workspace-write", windows_sandbox=None):
    if host not in {"codex", "claude"} or loading_mode not in {"native-discovery", "explicit-path"}:
        raise ValueError("Supported hosts: codex/claude; loading modes: native-discovery/explicit-path")
    if not model or model == "unrecorded" or not 1 <= timeout <= 3600:
        raise ValueError("An actual requested model and timeout between 1 and 3600 seconds are required")
    if sandbox not in {"read-only", "workspace-write"}:
        raise ValueError("Only read-only and workspace-write sandbox modes are supported")
    if windows_sandbox not in {None, "elevated", "unelevated"}:
        raise ValueError("Windows sandbox must be elevated or unelevated")
    if windows_sandbox is not None and (host != "codex" or sys.platform != "win32"):
        raise ValueError("--windows-sandbox applies only to Codex on native Windows")
    run_directory = Path(run_directory).resolve()
    if run_directory.is_relative_to(ROOT):
        raise ValueError("Raw evaluation runs must remain outside the source repository")
    run = json.loads((run_directory / "run.json").read_text(encoding="utf-8"))
    if run.get("status") != "not_run":
        raise ValueError("This run already has a reviewed result; prepare a new run")
    if run.get("host", "codex") != host:
        raise ValueError("Prepared host differs; prepare a new run with --host")
    if run.get("skill_loading_mode", "unrecorded") not in {"unrecorded", loading_mode}:
        raise ValueError("Execution loading mode contradicts the prepared run")
    if loading_mode == "native-discovery" and (run.get("prompt_explicit_skill") or
            (run.get("installed_skills") and "使用 $" in (run_directory / "prompt.txt").read_text(encoding="utf-8"))):
        raise ValueError("An explicitly named skill prompt cannot be labeled native-discovery")
    rubric_data = (run_directory / "rubric.json").read_bytes()
    rubric = json.loads(rubric_data)
    if (digest(json.dumps(rubric, ensure_ascii=False, sort_keys=True).encode()) != run["scenario_sha256"] or
            (run.get("rubric_sha256") and digest(rubric_data) != run["rubric_sha256"])):
        raise ValueError("Prepared rubric changed before execution; prepare a fresh run")
    if rubric.get("user_turns"):
        raise ValueError("Multi-turn scenarios are unsupported by this single-turn runner; no future turns are sent")
    project = (run_directory / "project").resolve()
    final_inventory(run_directory, run)
    if inventory(project) != run["initial_files"]:
        raise ValueError("Prepared files changed before execution; prepare a fresh run")
    if (git(project, "rev-parse", "HEAD") != run["baseline_commit"] or
            digest(git(project, "ls-files", "--stage").encode()) != run["starting_index_sha256"]):
        raise ValueError("Prepared HEAD or index changed before execution; prepare a fresh run")
    prompt = (run_directory / "prompt.txt").read_bytes()
    if run.get("prepared_prompt_sha256"):
        if digest(prompt) != run["prepared_prompt_sha256"]:
            raise ValueError("Prepared prompt changed before execution; prepare a fresh run")
    else:
        # Older prepared runs can be checked against their recorded scenario and deterministic prompt.
        expected_prompt = rubric["prompt"]
        explicit = rubric.get("explicit_skill")
        if explicit in run.get("installed_skills", []):
            expected_prompt = f"使用 ${explicit}（.agents/skills/{explicit}/SKILL.md）。\n\n" + expected_prompt
        if prompt.decode("utf-8").replace("\r\n", "\n") != expected_prompt + "\n":
            raise ValueError("Legacy prepared prompt does not match its recorded scenario")
    artifact = run_directory / "execution"
    artifact.mkdir()  # Exclusive directory creation reserves the run and prevents evidence replacement.
    metadata = {"format_version": 1, "host": host, "requested_model": model,
                "requested_configuration": {"model": model, "sandbox": sandbox if host == "codex" else None,
                                            "windows_sandbox": windows_sandbox, "approval_policy": None,
                                            "reasoning_effort": None},
                "loading_mode": loading_mode, "started_at": now(), "status": "starting",
                "project": str(project), "timeout_seconds": timeout, "prompt_sha256": digest(prompt),
                "input_validation": "prepared-byte-hashes" if run.get("prepared_prompt_sha256") and run.get("rubric_sha256")
                                    else "legacy-rubric-and-prompt-reconstruction",
                "criteria_status": "not_observed", "scored": False, "limitations": []}
    started = time.monotonic()
    process = None
    try:
        (artifact / "prompt.txt").write_bytes(prompt)
        binary = executable_path(host, executable)
        metadata["executable"] = str(binary)
        metadata["runtime"] = probe(binary, ["--version"], project, artifact).strip()
        help_args = ["exec", "--help"] if host == "codex" else ["--help"]
        help_text = probe(binary, help_args, project, artifact)
        required = (["--json", "--ignore-user-config", "--sandbox"] if host == "codex"
                    else ["--output-format", "--forward-subagent-text", "--include-hook-events",
                          "--permission-prompts", "--permission-mode", "--setting-sources", "--session-id"])
        if windows_sandbox is not None:
            required.append("--config")
        if any(option not in help_text for option in required):
            raise ValueError("Installed host lacks required safe/capture flags; see help.stdout")
        metadata["global_inputs_before"] = global_inputs(host)
        metadata["limitations"].extend([
            "Native project discovery is requested; actual catalog/selection must be confirmed in raw evidence.",
            "Known global inputs are hashed, but environment, auth, plugins, system policy and host memory are not fully isolated.",
            "Permission denials and host restrictions remain part of the evidence; no approval bypass is used."])
        if host == "claude":
            metadata["limitations"].append("acceptEdits permits requested file edits; commands requiring permission may be denied in no-prompt mode.")
        if windows_sandbox is not None:
            metadata["limitations"].append("Windows sandbox mode is a per-invocation config request; existing host setup/policy still determines availability.")
        session_id = str(uuid.uuid4()) if host == "claude" else None
        argv = host_argv(host, binary, project, model, session_id, sandbox, windows_sandbox)
        metadata["argv"] = argv
        (artifact / "argv.json").write_text(json.dumps(argv, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with (artifact / "stdout.jsonl").open("xb") as stdout, (artifact / "stderr.txt").open("xb") as stderr:
            process = launch_process(argv, project, stdout, stderr)
            metadata["pid"] = process.pid
            try:
                process.communicate(input=prompt, timeout=timeout)
                metadata["status"] = "completed" if process.returncode == 0 else "host_error"
            except subprocess.TimeoutExpired:
                stop_process(process)
                metadata["status"] = "timeout"
            metadata["exit_code"] = process.returncode
        events, _ = json_lines(artifact / "stdout.jsonl")
        if host == "codex":
            identifiers = {event.get("thread_id") for event in events if event.get("type") == "thread.started" and event.get("thread_id")}
            session_id = next(iter(identifiers)) if len(identifiers) == 1 else None
        metadata["session_id"] = session_id
        session, gap = copy_session(host, session_id, project, artifact, sessions)
        metadata["session"] = session
        if gap:
            metadata["limitations"].append(gap)
        metadata["observations"] = summarize(host, artifact / "stdout.jsonl", session, artifact, metadata["requested_configuration"])
        if not metadata["observations"]["tool_evidence_observed"]:
            metadata["limitations"].append("No raw tool evidence observed; process criteria must remain not_observed.")
    except KeyboardInterrupt:
        metadata.update({"status": "cancelled", "error": "KeyboardInterrupt: execution cancelled"})
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        metadata.update({"status": "runner_error", "error": f"{type(exc).__name__}: {exc}"})
    finally:
        if process is not None and process.poll() is None:
            try:
                stop_process(process)
            except (OSError, subprocess.SubprocessError) as exc:
                metadata["process_cleanup_error"] = str(exc)
        if process is not None:
            metadata["exit_code"] = process.returncode
            metadata["process_still_running"] = process.poll() is None
        # Interrupted and exceptional runs still preserve any obtainable partial transcript.
        if (artifact / "stdout.jsonl").exists() and "observations" not in metadata:
            try:
                events, _ = json_lines(artifact / "stdout.jsonl")
                identifiers = {event["thread_id"] for event in events if event.get("type") == "thread.started"
                               and isinstance(event.get("thread_id"), str)}
                partial_id = (next(iter(identifiers)) if len(identifiers) == 1 else None) if host == "codex" else session_id
                metadata["session_id"] = partial_id
                session, gap = copy_session(host, partial_id, project, artifact, sessions)
                metadata["session"] = session
                if gap:
                    metadata["limitations"].append(gap)
                metadata["observations"] = summarize(host, artifact / "stdout.jsonl", session, artifact, metadata["requested_configuration"])
            except (OSError, ValueError, TypeError, KeyError) as exc:
                metadata["partial_transcript_error"] = str(exc)
        metadata["finished_at"] = now()
        if "observations" in metadata:
            assessment = metadata["observations"]["configuration_comparison"]
            metadata["configuration_status"] = assessment["status"]
            if assessment["mismatch_observed"]:
                metadata["limitations"].append("Requested configuration differs from observed raw host context; affected runs cannot support an unqualified comparison.")
        metadata["elapsed_seconds"] = round(time.monotonic() - started, 6)
        metadata["global_inputs_after"] = global_inputs(host)
        try:
            metadata["final_files"] = final_inventory(run_directory, run)
            metadata["final_head"] = git(project, "rev-parse", "HEAD")
            metadata["final_status"] = git(project, "status", "--short")
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            metadata["final_snapshot_error"] = str(exc)
        metadata["artifact_sha256"] = inventory(artifact)
        (artifact / "execution.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="Prepared run directory outside the repository")
    parser.add_argument("--host", choices=["codex", "claude"], required=True)
    parser.add_argument("--model", required=True, help="Actual host model identifier")
    parser.add_argument("--loading-mode", choices=["native-discovery", "explicit-path"], default="native-discovery")
    parser.add_argument("--executable", type=Path, help="Native executable; shell/batch commands are never executed")
    parser.add_argument("--timeout", type=int, default=300, help="Finite model execution timeout, 1..3600 seconds")
    parser.add_argument("--sessions-root", type=Path, help="Existing host sessions/projects directory, only for raw export")
    parser.add_argument("--sandbox", choices=["read-only", "workspace-write"], default="workspace-write", help="Codex sandbox; Claude uses its own permission model")
    parser.add_argument("--windows-sandbox", choices=["elevated", "unelevated"], help="Codex native Windows only: per-invocation windows.sandbox override; no setup or automatic retry")
    args = parser.parse_args()
    try:
        result = execute(args.run, args.host, args.model, args.loading_mode, args.executable,
                         args.timeout, args.sessions_root, args.sandbox, args.windows_sandbox)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Execution rejected: {exc}\n")
    print(json.dumps({"execution_status": result["status"], "evidence": str(args.run.resolve() / "execution" / "execution.json"),
                      "configuration_status": result.get("configuration_status", "not_observed"),
                      "review_status": "not_run", "scored": False}, ensure_ascii=False))
    if result["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
