"""Smoke checks for isolated fixtures and the baseline/minimal/full comparison."""
from pathlib import Path
import importlib.util
import contextlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("eval_prepare", ROOT / "evals" / "prepare.py")
prepare_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_module)
RECORD_SPEC = importlib.util.spec_from_file_location("eval_record", ROOT / "evals" / "record.py")
record_module = importlib.util.module_from_spec(RECORD_SPEC)
sys.path.insert(0, str(ROOT / "evals"))
try:
    RECORD_SPEC.loader.exec_module(record_module)
finally:
    sys.path.pop(0)


class EvaluationFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="engineering-skills-eval-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def record_command(self, run_dir, trace, result="pass"):
        return [sys.executable, "-B", "-X", "utf8", str(ROOT / "evals" / "record.py"), str(run_dir),
                "--trace", str(trace), "--model", "unit-test-no-model", "--runtime", "unittest",
                "--loading-mode", "explicit-path", "--notes", "Synthetic recorder regression test only",
                "--criterion", "reproduction=pass", "--criterion", "regression=pass",
                "--criterion", f"claim-boundary={result}"]

    def test_modes_control_installed_skills_without_claiming_execution(self):
        for mode, expected in (("baseline", 0), ("minimal", 2), ("full", 9)):
            with self.subTest(mode=mode):
                run_dir = prepare_module.prepare("debug-explicit", mode, self.root / mode)
                run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
                self.assertEqual(len(run["installed_skills"]), expected)
                self.assertEqual(run["status"], "not_run")
                self.assertEqual(set(run["criteria"].values()), {"not_observed"})
                self.assertEqual(run["starting_status"], "")
                self.assertTrue(run["baseline_commit"])
                self.assertEqual(len(run["fixture_sha256"]), 64)
                self.assertFalse((run_dir / "project" / "rubric.json").exists())
                prompt = (run_dir / "prompt.txt").read_text(encoding="utf-8")
                self.assertEqual("$debug-work" in prompt, mode == "full")

    def test_review_has_tracked_and_untracked_changes(self):
        run_dir = prepare_module.prepare("review-untracked-explicit", "baseline", self.root / "review")
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertIn("invoice.py", run["starting_status"])
        self.assertIn("?? exporter.py", run["starting_status"])

    def test_never_overwrites_existing_run(self):
        output = self.root / "existing"
        output.mkdir()
        sentinel = output / "keep.txt"
        sentinel.write_text("existing evidence", encoding="utf-8")
        with self.assertRaises(ValueError):
            prepare_module.prepare("debug-explicit", "full", output)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "existing evidence")

    def test_recorder_requires_complete_scores_and_preserves_unknowns(self):
        run_dir = prepare_module.prepare("debug-explicit", "baseline", self.root / "record")
        trace = self.root / "synthetic-trace.txt"
        trace.write_text("Synthetic recorder unit test. No model or skill behavior was executed.", encoding="utf-8")
        command = [sys.executable, "-B", "-X", "utf8", str(ROOT / "evals" / "record.py"), str(run_dir),
                   "--trace", str(trace), "--model", "unit-test-no-model", "--runtime", "unittest",
                   "--loading-mode", "explicit-path", "--notes", "Synthetic recorder test only",
                   "--criterion", "reproduction=not_observed"]
        rejected = subprocess.run(command, capture_output=True)
        self.assertNotEqual(rejected.returncode, 0)
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(run["status"], "not_run")
        accepted = subprocess.run(command + ["--criterion", "regression=not_observed",
                                              "--criterion", "claim-boundary=not_observed"], capture_output=True)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(run["status"], "inconclusive")
        self.assertEqual(run["evidence"]["trace_sha256"], prepare_module.digest(trace.read_bytes()))

    def test_recorder_rejects_conflicting_saved_trace_without_mutation(self):
        run_dir = prepare_module.prepare("debug-explicit", "baseline", self.root / "conflict")
        saved = run_dir / "trace.txt"
        saved.write_text("Existing evidence must survive.", encoding="utf-8")
        replacement = self.root / "different-trace.txt"
        replacement.write_text("Different synthetic evidence.", encoding="utf-8")
        original_run = (run_dir / "run.json").read_bytes()
        result = subprocess.run(self.record_command(run_dir, replacement), capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"will not be overwritten", result.stderr)
        self.assertEqual(saved.read_text(encoding="utf-8"), "Existing evidence must survive.")
        self.assertEqual((run_dir / "run.json").read_bytes(), original_run)
        self.assertFalse((run_dir / ".record.lock").exists())

    def test_recorder_reuses_same_or_identical_trace(self):
        for same_path in (True, False):
            with self.subTest(same_path=same_path):
                run_dir = prepare_module.prepare("debug-explicit", "baseline", self.root / f"reuse-{same_path}")
                saved = run_dir / "trace.txt"
                saved.write_text("Same synthetic evidence.", encoding="utf-8")
                supplied = saved if same_path else self.root / "identical-trace.txt"
                if not same_path:
                    supplied.write_bytes(saved.read_bytes())
                result = subprocess.run(self.record_command(run_dir, supplied), capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
                self.assertEqual(run["status"], "pass")
                self.assertTrue(run["final_files"])

    def test_recorder_rejects_deleted_project_without_mutation(self):
        run_dir = prepare_module.prepare("debug-explicit", "baseline", self.root / "deleted")
        trace = self.root / "deleted-trace.txt"
        trace.write_text("Synthetic evidence with a lost workspace.", encoding="utf-8")
        original_run = (run_dir / "run.json").read_bytes()
        project = (run_dir / "project").resolve()
        # Verify the absolute deletion target remains within this test's temporary directory.
        self.assertTrue(project.is_relative_to(self.root.resolve()))
        self.assertEqual(project, run_dir.resolve() / "project")

        def remove_readonly(function, path, error):
            os.chmod(path, stat.S_IWRITE)
            function(path)

        shutil.rmtree(project, onerror=remove_readonly)
        self.assertFalse(project.exists())
        result = subprocess.run(self.record_command(run_dir, trace), capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"missing, moved", result.stderr)
        self.assertEqual((run_dir / "run.json").read_bytes(), original_run)
        self.assertFalse((run_dir / "trace.txt").exists())

    def test_recorder_rejects_foreign_project_and_missing_baseline(self):
        for damage in ("foreign-project", "missing-baseline"):
            with self.subTest(damage=damage):
                run_dir = prepare_module.prepare("debug-explicit", "baseline", self.root / damage)
                other_run = prepare_module.prepare("debug-explicit", "baseline", self.root / (damage + "-other"))
                metadata_path = run_dir / "run.json"
                run = json.loads(metadata_path.read_text(encoding="utf-8"))
                if damage == "foreign-project":
                    run["project"] = str(other_run / "project")
                else:
                    run["baseline_commit"] = "0" * 40
                metadata_path.write_text(json.dumps(run), encoding="utf-8")
                original_run = metadata_path.read_bytes()
                trace = self.root / f"{damage}-trace.txt"
                trace.write_text("Synthetic evidence.", encoding="utf-8")
                result = subprocess.run(self.record_command(run_dir, trace), capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(metadata_path.read_bytes(), original_run)
                self.assertFalse((run_dir / "trace.txt").exists())

    def test_recorder_allows_changed_head_to_be_recorded_as_failure(self):
        run_dir = prepare_module.prepare("debug-explicit", "baseline", self.root / "changed-head")
        prepare_module.git(run_dir / "project", "commit", "--allow-empty", "-m", "Synthetic unauthorized agent commit")
        trace = self.root / "changed-head-trace.txt"
        trace.write_text("Synthetic trace: agent committed when it was not authorized.", encoding="utf-8")
        result = subprocess.run(self.record_command(run_dir, trace, result="fail"), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(run["status"], "fail")

    def test_recorder_atomic_write_failure_preserves_previous_evidence(self):
        run_dir = prepare_module.prepare("debug-explicit", "baseline", self.root / "atomic-failure")
        saved = run_dir / "trace.txt"
        saved.write_text("Existing evidence for the simulated I/O failure.", encoding="utf-8")
        original_run = (run_dir / "run.json").read_bytes()
        original_trace = saved.read_bytes()
        arguments = self.record_command(run_dir, saved)[4:]
        with mock.patch.object(sys, "argv", arguments), mock.patch.object(record_module.os, "replace", side_effect=OSError("simulated failure")):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                record_module.main()
        self.assertEqual(error.exception.code, 1)
        self.assertEqual((run_dir / "run.json").read_bytes(), original_run)
        self.assertEqual(saved.read_bytes(), original_trace)
        self.assertFalse((run_dir / ".record.lock").exists())
        self.assertFalse(list(run_dir.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
