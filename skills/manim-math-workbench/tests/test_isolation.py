import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installed_runner", ROOT / "scripts/video.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class IsolationTests(unittest.TestCase):
    def test_stale_project_cannot_select_old_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "runtime.json"
            config.write_text(json.dumps({
                **{key: sys.executable for key in
                   ("python_exe", "ffmpeg_exe", "whisper_exe", "whisper_model")},
                "manim_project": str(Path(directory) / "removed-old-project"),
                "engine_root": str(Path(directory) / "removed-old-engine"),
            }), encoding="utf-8")
            self.assertEqual(runner._runtime_config(config)["manim_project"], str(runner.ENGINE_ROOT))

    def test_other_python_always_delegates_even_with_dependencies(self):
        other = Path(sys.executable).with_name("other-python.exe")
        with patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 7)) as run:
            self.assertEqual(runner._reexec_with_runtime({"python_exe": str(other)}, ["run"]), 7)
            self.assertEqual(run.call_args.args[0][:2], [str(other.resolve()), "-I"])

    def test_same_isolated_python_does_not_recurse(self):
        with patch.object(runner.sys, "flags") as flags, patch.object(runner.subprocess, "run") as run:
            flags.isolated = 1
            self.assertIsNone(runner._reexec_with_runtime({"python_exe": sys.executable}, []))
            run.assert_not_called()

    def test_nonisolated_python_restarts_isolated(self):
        with patch.object(runner.sys, "flags") as flags, patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            flags.isolated = 0
            self.assertEqual(runner._reexec_with_runtime({"python_exe": sys.executable}, []), 0)
            self.assertEqual(run.call_args.args[0][1], "-I")

    def test_runtime_evidence_uses_installed_modules(self):
        config = {key: sys.executable for key in ("ffmpeg_exe", "whisper_exe", "whisper_model")}
        config["manim_project"] = str(runner.ENGINE_ROOT)
        evidence = runner._runtime_evidence(config)
        for name, path in evidence["module_files"].items():
            if name.startswith("v3."):
                self.assertTrue(Path(path).is_relative_to(runner.ENGINE_ROOT))
        self.assertEqual(evidence["sys_executable"], sys.executable)

    def test_render_records_command_and_error(self):
        from v3.rendering import _run_render
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "render.log"
            command = [sys.executable, "-I", "-c", "raise RuntimeError('isolation-test')"]
            with self.assertRaises(RuntimeError):
                _run_render(command, Path(directory), 20, log, "render: ")
            self.assertIn("isolation-test", log.read_text(encoding="utf-8"))
            record = json.loads(log.with_suffix(".command.json").read_text(encoding="utf-8"))
            self.assertEqual(record["command"], command)


if __name__ == "__main__":
    unittest.main()
