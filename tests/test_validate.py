"""Mutation tests run in disposable package copies, never against source files."""
from pathlib import Path
import importlib.util
import json
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("package_validator", ROOT / "scripts" / "validate.py")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class PackageValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="engineering-skills-validation-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("skills", "licenses"):
            shutil.copytree(ROOT / name, self.root / name)
        shutil.copy2(ROOT / "sources.json", self.root / "sources.json")

    def codes(self, **kwargs):
        return {issue["code"] for issue in validator.validate(self.root, **kwargs)["issues"]}

    def test_current_package_passes(self):
        result = validator.validate(self.root)
        self.assertTrue(result["ok"], result["issues"])

    def test_detects_distribution_drift(self):
        path = self.root / "skills" / "tdd" / "tests.md"
        path.write_bytes(path.read_bytes() + b"\nUnexpected change.\n")
        self.assertIn("hash.distributed", self.codes())

    def test_detects_broken_link_independently_of_hash(self):
        path = self.root / "skills" / "tdd" / "SKILL.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n[Missing](missing-file.md)\n", encoding="utf-8")
        manifest_path = self.root / "sources.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            if entry["destination"] == "skills/tdd/SKILL.md":
                entry["distributed_sha256"] = validator.sha256(path.read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        codes = self.codes()
        self.assertIn("link.missing", codes)
        self.assertNotIn("hash.distributed", codes)

    def test_selection_requires_dependency(self):
        self.assertIn("dependency.missing", self.codes(selected={"implement-work"}))

    def test_minimal_selection_passes(self):
        self.assertFalse(self.codes(selected={"decision-notes", "implement-work"}))

    def test_detects_license_loss(self):
        (self.root / "skills" / "tdd" / "LICENSE").unlink()
        self.assertIn("license.read", self.codes())

    def test_frontmatter_directory_mismatch(self):
        path = self.root / "skills" / "tdd" / "SKILL.md"
        path.write_text(path.read_text(encoding="utf-8").replace("name: tdd", "name: incorrect-name", 1), encoding="utf-8")
        self.assertIn("skill.name", self.codes())


if __name__ == "__main__":
    unittest.main()
