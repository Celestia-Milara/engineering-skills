"""Check corpus validity and isolation; these tests do not measure model routing."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
import triggers


class TriggerCorpusTests(unittest.TestCase):
    def test_bilingual_corpus_covers_all_skills_and_negative_neighbors(self):
        cases = triggers.load_suite()["cases"]
        self.assertEqual(len(cases), 28)
        self.assertEqual(sum(c["language"] == "zh" for c in cases), 14)
        self.assertEqual(sum(c["language"] == "en" for c in cases), 14)
        covered = {s for c in cases for s in c["expected_skills"]}
        self.assertEqual(covered, {p.name for p in (ROOT / "skills").iterdir() if p.is_dir()})
        self.assertTrue(any(not c["expected_skills"] for c in cases))

    def test_preparation_keeps_routing_labels_outside_actor_project(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "evals" / "triggers.py"),
                                     "trigger-copy-en", "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = json.loads((output / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run["skill_loading_mode"], "native-discovery")
            self.assertEqual(set(run["criteria"]), {"selection", "scope"})
            self.assertNotIn("$implement-work", (output / "prompt.txt").read_text(encoding="utf-8"))
            for path in (output / "project").rglob("*"):
                self.assertNotIn(path.name, {"rubric.json", "triggers.json"})

    def test_other_packages_cannot_be_scored_against_full_routing_labels(self):
        from prepare import prepare
        with self.assertRaises(ValueError):
            prepare("trigger-debug-en", "minimal", suite_path=triggers.SUITE)


if __name__ == "__main__":
    unittest.main()
