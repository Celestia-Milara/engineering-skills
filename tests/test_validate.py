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
        for name in ("skills", "licenses", "templates"):
            shutil.copytree(ROOT / name, self.root / name)
        shutil.copy2(ROOT / "AGENTS.example.md", self.root / "AGENTS.example.md")
        (self.root / "README.md").write_text("# Package fixture\n", encoding="utf-8")
        shutil.copy2(ROOT / "sources.json", self.root / "sources.json")
        shutil.copy2(ROOT / "LICENSE", self.root / "LICENSE")

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

    def test_original_skill_can_be_selected_alone(self):
        self.assertFalse(self.codes(selected={"git-work"}))

    def test_original_distribution_drift_is_detected(self):
        path = self.root / "skills" / "git-work" / "SKILL.md"
        path.write_bytes(path.read_bytes() + b"\nUnreviewed original change.\n")
        self.assertIn("hash.distributed", self.codes())

    def test_original_provenance_rejects_upstream_claim(self):
        manifest_path = self.root / "sources.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        adapted = next(entry for entry in manifest["files"] if entry["treatment"] == "adapted")
        original = next(entry for entry in manifest["files"] if entry["destination"] == "skills/git-work/SKILL.md")
        original["source_files"] = adapted["source_files"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertIn("manifest.original", self.codes())

    def test_original_mapping_must_match_entrypoint(self):
        manifest_path = self.root / "sources.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["skill_sources"]["git-work"] = "mattpocock"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertIn("manifest.original", self.codes())

    def test_original_license_must_match_package_license(self):
        license_path = self.root / "skills" / "git-work" / "LICENSE"
        license_path.write_bytes(license_path.read_bytes() + b"\nChanged license.\n")
        self.assertIn("license.content", self.codes())

    def test_shared_copy_drift_cannot_be_accepted_by_refreshing_hash(self):
        path = self.root / "skills" / "implement-work" / "references" / "git-safety.md"
        path.write_bytes(path.read_bytes().replace("dirty 工作区本身不要求停止。".encode(), b"Stop on any dirty tree."))
        manifest_path = self.root / "sources.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            if entry["destination"] == path.relative_to(self.root).as_posix():
                entry["distributed_sha256"] = validator.sha256(path.read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertIn("shared.drift", self.codes())
        self.assertNotIn("hash.distributed", self.codes())

    def test_shared_template_drift_is_detected(self):
        path = self.root / "AGENTS.example.md"
        path.write_bytes(path.read_bytes().replace("dirty 工作区本身不要求停止。".encode(), b"Always stop."))
        self.assertIn("shared.drift", self.codes())

    def test_unregistered_shared_copy_is_detected(self):
        manifest_path = self.root / "sources.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["shared_rules"][0]["copies"].remove("templates/AGENTS.snippet.md")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertIn("shared.unregistered", self.codes())

    def test_broken_shared_marker_is_detected(self):
        path = self.root / "skills" / "debug-work" / "references" / "git-safety.md"
        path.write_bytes(path.read_bytes().replace(b"<!-- /shared-rule: git-safety -->", b""))
        self.assertIn("shared.marker", self.codes())

    def test_detects_license_loss(self):
        (self.root / "skills" / "tdd" / "LICENSE").unlink()
        self.assertIn("license.read", self.codes())

    def test_frontmatter_directory_mismatch(self):
        path = self.root / "skills" / "tdd" / "SKILL.md"
        path.write_text(path.read_text(encoding="utf-8").replace("name: tdd", "name: incorrect-name", 1), encoding="utf-8")
        self.assertIn("skill.name", self.codes())


if __name__ == "__main__":
    unittest.main()
