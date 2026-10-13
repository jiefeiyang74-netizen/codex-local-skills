"""Check installation safety in temporary directories, never real user skills."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("skill_installer", ROOT / "tools" / "install_skills.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerSafetyTests(unittest.TestCase):
    def test_dry_run_does_not_create_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "new" / "skills"
            plan = installer.install(["app-factory"], target, dry_run=True)
            self.assertEqual(len(plan), 1)
            self.assertFalse(target.exists())

    def test_install_refuses_overwrite_and_preserves_previous_version(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            installer.install(["app-factory"], target)
            marker = target / "app-factory" / "local-changes.txt"
            marker.write_text("private local changes", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                installer.install(["app-factory"], target)
            self.assertEqual(marker.read_text(encoding="utf-8"), "private local changes")
            installer.install(["app-factory"], target, replace=True)
            backups = list((target / ".backups").glob("app-factory-*/local-changes.txt"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "private local changes")
            self.assertFalse(marker.exists())

    def test_selection_rejects_path_traversal_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "skills"
            with self.assertRaises(ValueError):
                installer.install(["../outside"], target)
            self.assertFalse(target.exists())

    def test_all_selection_is_preflighted_before_any_install(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            (target / "replace-logo-with-cutout").mkdir()
            with self.assertRaises(FileExistsError):
                installer.install(list(installer.SKILLS), target)
            self.assertFalse((target / "app-factory").exists())

    def test_target_inside_source_is_rejected_before_copy(self):
        with self.assertRaises(ValueError):
            installer.install(["app-factory"], ROOT / "skills" / "app-factory" / "nested")

    def test_replacing_source_is_rejected(self):
        with self.assertRaises(ValueError):
            installer.install(["app-factory"], ROOT / "skills", replace=True)

    def test_batch_failure_reports_retained_completed_install(self):
        original_copytree = installer.shutil.copytree
        def interrupted_copytree(source, destination, *args, **kwargs):
            if Path(source).name == "replace-logo-with-cutout":
                raise OSError("simulated copy failure")
            return original_copytree(source, destination, *args, **kwargs)
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            with patch.object(installer.shutil, "copytree", interrupted_copytree):
                with self.assertRaisesRegex(RuntimeError, "Already completed"):
                    installer.install(["app-factory", "replace-logo-with-cutout"], target)
            self.assertTrue((target / "app-factory" / "SKILL.md").is_file())
            self.assertFalse((target / "replace-logo-with-cutout").exists())


if __name__ == "__main__":
    unittest.main()
