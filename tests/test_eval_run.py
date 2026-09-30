"""Raw host capture regressions. Fake subprocesses do not execute a model."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
try:
    import prepare
    import run as runner
finally:
    sys.path.pop(0)


class HeadlessCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="engineering-skills-capture-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def prepared(self, name, case="debug-explicit", **kwargs):
        return prepare.prepare(case, "baseline", self.root / name, **kwargs)

    def fake_host(self, run_directory, mode="tools"):
        sessions = self.root / "sessions"
        sessions.mkdir(exist_ok=True)
        script = self.root / f"fake-{run_directory.name}.py"
        script.write_text(
            "import json, pathlib, sys, time\n"
            "prompt = sys.stdin.buffer.read()\n"
            f"mode = {mode!r}\n"
            "identifier = '11111111-2222-3333-4444-555555555555'\n"
            "print(json.dumps({'type':'thread.started','thread_id':identifier}), flush=True)\n"
            "print('synthetic stderr, no model', file=sys.stderr, flush=True)\n"
            "if mode == 'timeout': time.sleep(60)\n"
            "if mode == 'error': sys.exit(7)\n"
            "events = [{'type':'session_meta','payload':{'id':identifier,'cwd':str(pathlib.Path.cwd())}}]\n"
            "if mode == 'tools':\n"
            " events += [{'type':'turn_context','payload':{'model':'fake-observed-model','sandbox_policy':{'type':'read-only'},'approval_policy':'never','effort':'medium'}},\n"
            " {'type':'response_item','payload':{'type':'function_call','call_id':'call-1','name':'exec_command','arguments':'synthetic'}},\n"
            " {'type':'response_item','payload':{'type':'function_call_output','call_id':'call-1','output':'synthetic output'}}]\n"
            f"session = pathlib.Path({str(sessions)!r}) / ('rollout-' + identifier + '.jsonl')\n"
            "session.write_text('\\n'.join(json.dumps(event) for event in events) + '\\n', encoding='utf-8')\n"
            "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':12,'output_tokens':3}}), flush=True)\n"
            "if mode == 'bad-json': print('not-json', flush=True)\n",
            encoding="utf-8")
        return script, sessions

    def execute_fake(self, run_directory, mode="tools", timeout=10):
        script, sessions = self.fake_host(run_directory, mode)
        def fake_probe(executable, args, directory, artifact):
            text = "fake-host 1.0" if args == ["--version"] else "--json --ignore-user-config --sandbox"
            (artifact / ("version.stdout" if args == ["--version"] else "help.stdout")).write_text(text, encoding="utf-8")
            return text

        with mock.patch.object(runner, "probe", side_effect=fake_probe), \
                mock.patch.object(runner, "host_argv", return_value=[sys.executable, str(script)]), \
                mock.patch.object(runner, "global_inputs", return_value=[]):
            return runner.execute(run_directory, "codex", "fake-requested-model", executable=sys.executable,
                                  timeout=timeout, sessions=sessions)

    def test_raw_capture_exports_verified_session_usage_without_grading(self):
        directory = self.prepared("raw")
        original_run = (directory / "run.json").read_bytes()
        result = self.execute_fake(directory)
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["scored"])
        self.assertEqual(result["criteria_status"], "not_observed")
        self.assertEqual(result["session"]["codex_tool_calls"], 1)
        self.assertEqual(result["session"]["codex_tool_results"], 1)
        self.assertTrue(result["observations"]["tool_evidence_observed"])
        self.assertEqual(result["observations"]["actual_models"], ["fake-observed-model"])
        self.assertEqual(result["observations"]["actual_sandbox_policies"], [{"type": "read-only"}])
        self.assertEqual(result["observations"]["actual_approval_policies"], ["never"])
        self.assertEqual(result["observations"]["actual_reasoning_efforts"], ["medium"])
        sandbox = result["observations"]["configuration_comparison"]["fields"]["sandbox"]
        self.assertEqual(sandbox, {"requested": "workspace-write", "observed": ["read-only"], "status": "mismatch"})
        self.assertEqual(result["configuration_status"], "mismatch")
        self.assertEqual(result["observations"]["usage_events"][0]["usage"]["input_tokens"], 12)
        self.assertEqual(result["observations"]["completeness"], "requires_manual_review")
        self.assertEqual((directory / "run.json").read_bytes(), original_run)
        self.assertIn(b"synthetic stderr", (directory / "execution" / "stderr.txt").read_bytes())
        self.assertEqual((directory / "execution" / "prompt.txt").read_bytes(), (directory / "prompt.txt").read_bytes())
        self.assertNotIn("rubric", " ".join(result["argv"]))

    def test_missing_tools_does_not_create_process_evidence(self):
        result = self.execute_fake(self.prepared("no-tools"), "no-tools")
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["observations"]["tool_evidence_observed"])
        self.assertEqual(result["observations"]["actual_sandbox_policies"], [])
        self.assertEqual(result["configuration_status"], "not_observed")
        self.assertIn("No raw tool evidence", " ".join(result["limitations"]))
        self.assertFalse(result["scored"])

    def test_host_error_and_timeout_preserve_partial_logs(self):
        for mode in ("error", "timeout"):
            with self.subTest(mode=mode):
                directory = self.prepared(mode)
                result = self.execute_fake(directory, mode, timeout=1)
                self.assertEqual(result["status"], "host_error" if mode == "error" else "timeout")
                self.assertTrue((directory / "execution" / "stdout.jsonl").read_bytes())
                self.assertTrue((directory / "execution" / "stderr.txt").read_bytes())
                self.assertTrue((directory / "execution" / "execution.json").is_file())
                self.assertEqual(json.loads((directory / "run.json").read_text(encoding="utf-8"))["status"], "not_run")

    def test_existing_evidence_is_never_overwritten(self):
        directory = self.prepared("reserved")
        self.execute_fake(directory)
        original = (directory / "execution" / "execution.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.execute_fake(directory)
        self.assertEqual((directory / "execution" / "execution.json").read_bytes(), original)

    def test_multiturn_and_moved_initial_state_fail_before_host_launch(self):
        directory = self.prepared("multiturn", "interview-multiturn-explicit")
        with mock.patch.object(runner.subprocess, "Popen") as process:
            with self.assertRaisesRegex(ValueError, "Multi-turn"):
                runner.execute(directory, "codex", "fake")
            process.assert_not_called()
        other = self.prepared("modified")
        (other / "project" / "average.py").write_text("foreign edit", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed before"):
            runner.execute(other, "codex", "fake")
        self.assertFalse((directory / "execution").exists())
        self.assertFalse((other / "execution").exists())

    def test_mismatched_session_is_not_copied(self):
        directory = self.prepared("mismatch")
        artifact = self.root / "artifact"
        artifact.mkdir()
        sessions = self.root / "wrong-sessions"
        sessions.mkdir()
        identifier = "11111111-2222-3333-4444-555555555555"
        (sessions / f"rollout-{identifier}.jsonl").write_text(json.dumps({"type": "session_meta", "payload": {
            "id": identifier, "cwd": str(self.root / "different-project")}}), encoding="utf-8")
        session, gap = runner.copy_session("codex", identifier, directory / "project", artifact, sessions)
        self.assertIsNone(session)
        self.assertIn("found 0", gap)
        self.assertFalse((artifact / "session.jsonl").exists())

    def test_explicit_prompt_and_conflicting_loading_mode_are_rejected(self):
        directory = prepare.prepare("debug-explicit", "full", self.root / "explicit", loading_mode="explicit-path")
        with self.assertRaisesRegex(ValueError, "contradicts"):
            runner.execute(directory, "codex", "fake", loading_mode="native-discovery")
        metadata = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        metadata["skill_loading_mode"] = "unrecorded"
        (directory / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "explicitly named"):
            runner.execute(directory, "codex", "fake", loading_mode="native-discovery")
        self.assertFalse((directory / "execution").exists())

    def test_invalid_json_remains_raw_and_is_reported(self):
        directory = self.prepared("bad-json")
        result = self.execute_fake(directory, "bad-json")
        self.assertEqual(len(result["observations"]["stdout_parse_errors"]), 1)
        self.assertIn(b"not-json", (directory / "execution" / "stdout.jsonl").read_bytes())

    def test_modified_prompt_or_rubric_is_rejected_before_launch(self):
        for target in ("prompt.txt", "rubric.json"):
            with self.subTest(target=target):
                directory = self.prepared("changed-" + target)
                path = directory / target
                if target == "prompt.txt":
                    path.write_bytes(b"modified request\n")
                else:
                    rubric = json.loads(path.read_text(encoding="utf-8"))
                    rubric["prompt"] = "modified request"
                    path.write_text(json.dumps(rubric), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "changed before"):
                    runner.execute(directory, "codex", "fake")
                self.assertFalse((directory / "execution").exists())

    def test_legacy_prepared_input_is_bound_to_recorded_scenario(self):
        directory = self.prepared("legacy")
        path = directory / "run.json"
        metadata = json.loads(path.read_text(encoding="utf-8"))
        metadata.pop("prepared_prompt_sha256")
        metadata.pop("rubric_sha256")
        path.write_text(json.dumps(metadata), encoding="utf-8")
        result = self.execute_fake(directory)
        self.assertEqual(result["input_validation"], "legacy-rubric-and-prompt-reconstruction")
        self.assertEqual(result["status"], "completed")

    def test_commands_use_safe_host_flags_and_exact_argument_arrays(self):
        project = Path("project with spaces")
        for host in ("codex", "claude"):
            argv = runner.host_argv(host, Path("host with spaces.exe"), project, "model-name", "session-id")
            self.assertIsInstance(argv, list)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
            self.assertNotIn("--dangerously-skip-permissions", argv)
            if host == "codex":
                self.assertIn("--ignore-user-config", argv)
                self.assertIn("--sandbox", argv)
                self.assertNotIn("--ephemeral", argv)
                self.assertNotIn("--full-auto", argv)
            else:
                self.assertIn("--permission-prompts", argv)
                self.assertIn("--setting-sources", argv)

    def test_cancellation_stops_owned_host_before_final_snapshot(self):
        directory = self.prepared("cancelled")
        sequence = []

        class InterruptedProcess:
            pid = 12345
            returncode = None

            def __init__(self, argv, project, stdout, stderr):
                stdout.write(b'{"type":"thread.started","thread_id":"11111111-2222-3333-4444-555555555555"}\n')

            def poll(self):
                return self.returncode

            def communicate(self, **kwargs):
                raise KeyboardInterrupt

        def stop_owned(process):
            sequence.append("stop")
            process.returncode = -1

        real_snapshot = runner.final_inventory

        def snapshot(*args):
            sequence.append("snapshot")
            return real_snapshot(*args)

        with mock.patch.object(runner, "executable_path", return_value=Path(sys.executable)), \
                mock.patch.object(runner, "probe", side_effect=["fake-host 1", "--json --ignore-user-config --sandbox"]), \
                mock.patch.object(runner, "global_inputs", return_value=[]), \
                mock.patch.object(runner, "launch_process", InterruptedProcess), \
                mock.patch.object(runner, "stop_process", side_effect=stop_owned), \
                mock.patch.object(runner, "final_inventory", side_effect=snapshot):
            result = runner.execute(directory, "codex", "fake-requested-model", sessions=self.root / "absent")
        self.assertEqual(result["status"], "cancelled")
        self.assertFalse(result["process_still_running"])
        self.assertEqual(sequence, ["snapshot", "stop", "snapshot"])
        self.assertIn("observations", result)
        self.assertTrue((directory / "execution" / "execution.json").is_file())

    def test_windows_sandbox_override_is_explicit_per_invocation(self):
        argv = runner.host_argv("codex", Path("codex.exe"), self.root, "model", windows_sandbox="elevated")
        self.assertEqual(argv[argv.index("-c") + 1], 'windows.sandbox="elevated"')
        default = runner.host_argv("codex", Path("codex.exe"), self.root, "model")
        self.assertNotIn("-c", default)
        with self.assertRaisesRegex(ValueError, "Windows sandbox must"):
            runner.execute(self.root / "absent", "codex", "fake", windows_sandbox="disabled")
        with self.assertRaisesRegex(ValueError, "only to Codex"):
            runner.execute(self.root / "absent", "claude", "fake", windows_sandbox="elevated")
        with mock.patch.object(runner.sys, "platform", "linux"), self.assertRaisesRegex(ValueError, "native Windows"):
            runner.execute(self.root / "absent", "codex", "fake", windows_sandbox="elevated")

    def test_multiple_runtime_contexts_and_unobserved_windows_implementation(self):
        directory = self.root / "context-summary"
        directory.mkdir()
        stdout = directory / "stdout.jsonl"
        stdout.write_bytes(b'{}\n')
        events = [{"type": "turn_context", "payload": {"model": "model", "sandbox_policy": {"type": "workspace-write", "writable_roots": ["project"]},
                                                            "approval_policy": "never", "effort": "medium"}},
                  {"type": "turn_context", "payload": {"model": "model", "sandbox_policy": {"type": "read-only"},
                                                            "approval_policy": "on-request", "collaboration_mode": {"settings": {"reasoning_effort": "high"}}}}]
        (directory / "session.jsonl").write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")
        result = runner.summarize("codex", stdout, {"path": "session.jsonl"}, directory,
                                  {"model": "model", "sandbox": "workspace-write", "windows_sandbox": "elevated"})
        comparison = result["configuration_comparison"]
        self.assertEqual(comparison["fields"]["sandbox"]["status"], "mismatch")
        self.assertEqual(comparison["fields"]["model"]["status"], "match")
        self.assertEqual(comparison["fields"]["windows_sandbox"]["status"], "not_observed")
        self.assertEqual(result["actual_approval_policies"], ["never", "on-request"])
        self.assertEqual(result["actual_reasoning_efforts"], ["high", "medium"])
        self.assertEqual(len(result["runtime_contexts"]), 2)
        self.assertEqual(result["runtime_contexts"][1]["reasoning_effort_source"], "collaboration_mode.settings.reasoning_effort")
        self.assertTrue(comparison["requires_manual_review"])


if __name__ == "__main__":
    unittest.main()
