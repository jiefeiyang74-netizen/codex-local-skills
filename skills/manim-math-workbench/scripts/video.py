"""Offline Windows runner for the distributable Manim math-video skill.

The runner deliberately keeps planning outside this module: Codex (or a
human) supplies a storyboard JSON, while this package validates, aligns,
compiles, renders, and records an auditable job.  No network or paid API is
used here.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")


RUNNER_VERSION = "0.1.2"
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = PACKAGE_ROOT / "assets" / "engine"
PROMPT_PATH = PACKAGE_ROOT / "assets" / "engine" / "prompts" / "animation_director.md"

if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from v3.capabilities import (  # noqa: E402
    ACTION_FIELDS,
    ALLOWED_ACTIONS,
    ALLOWED_KINDS,
    CAPABILITY_VERSION,
)
from v3.storyboard import (  # noqa: E402
    SCHEMA_VERSION,
    STORYBOARD_SYSTEM_PROMPT,
    StoryboardValidationError,
    normalize_storyboard,
    storyboard_timeline,
)


class RunnerError(RuntimeError):
    """An actionable failure that should make the CLI exit non-zero."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _json_load(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise RunnerError(f"{label} 不存在：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunnerError(f"{label} 不是有效 UTF-8 JSON：{path}") from exc
    if not isinstance(payload, dict):
        raise RunnerError(f"{label} 必须是 JSON 对象：{path}")
    return payload


def _resolve_input(value: str, base: Path) -> Path:
    candidate = Path(str(value))
    return candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()


def _require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise RunnerError(f"{label} 不存在或不是文件：{path}")
    return path


def _runtime_config(path: Path) -> dict[str, Any]:
    raw = _json_load(path, "runtime-config")
    required = ("python_exe", "ffmpeg_exe", "whisper_exe", "whisper_model")
    resolved: dict[str, Any] = {"config_path": str(path.resolve())}
    for key in required:
        value = str(raw.get(key) or "").strip()
        if not value:
            raise RunnerError(f"runtime-config 缺少字段：{key}")
        resolved[key] = str(_require_file(_resolve_input(value, path.parent), key))
    # A shared runtime may have been provisioned by a different package copy.
    # Never inherit that copy's project directory or its manim.cfg/imports.
    resolved["manim_project"] = str(ENGINE_ROOT)
    return resolved


def _request(path: Path) -> tuple[dict[str, Any], Path]:
    raw = _json_load(path, "request")
    missing = [key for key in ("problem", "narration", "audio_path") if not str(raw.get(key) or "").strip()]
    if missing:
        raise RunnerError("request 缺少必填字段：" + ", ".join(missing))
    audio = _resolve_input(str(raw["audio_path"]), path.parent)
    _require_file(audio, "request.audio_path")
    request = dict(raw)
    request["problem"] = str(request["problem"]).strip()
    request["narration"] = str(request["narration"]).strip()
    request["audio_path"] = str(audio)
    request.setdefault("title", "数学解题可视化")
    request["planner_mode"] = "model"
    return request, audio


def _job_dir(value: str) -> Path:
    job = Path(value).expanduser().resolve()
    job.mkdir(parents=True, exist_ok=True)
    if not job.is_dir():
        raise RunnerError(f"job-dir 不是目录：{job}")
    return job


def _new_attempt(root: Path) -> Path:
    """Allocate an immutable attempt directory so reruns never overwrite media."""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    attempt = root / "runs" / run_id
    attempt.mkdir(parents=True, exist_ok=False)
    return attempt


def _redacted_command(command: list[str]) -> list[str]:
    # Paths are useful for diagnosis; request text and model prompts never go
    # through this command list.  Keep this helper as a single audit point.
    return [str(item) for item in command]


def _run_checked(command: list[str], cwd: Path, log_path: Path, timeout: int) -> None:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerError(f"外部命令未能完成：{command[0]}：{exc}") from exc
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    log_path.write_text(
        json.dumps(
            {"command": _redacted_command(command), "returncode": completed.returncode,
             "stdout": stdout[-12000:], "stderr": stderr[-12000:]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if completed.returncode:
        raise RunnerError(f"外部命令失败（{completed.returncode}），详见：{log_path}")


def _alignment_audio(audio: Path, ffmpeg: Path, job: Path) -> Path:
    if audio.suffix.lower() in {".wav", ".mp3", ".flac", ".ogg", ".m4a"}:
        return audio
    converted = job / "alignment_input.wav"
    command = [
        str(ffmpeg), "-y", "-i", str(audio), "-ac", "1", "-ar", "16000", str(converted)
    ]
    _run_checked(command, job, job / "ffmpeg_alignment.log.json", 300)
    return _require_file(converted, "ffmpeg 转换音频")


def _engine_version() -> str:
    return f"runner-{RUNNER_VERSION};capability-{CAPABILITY_VERSION};schema-{SCHEMA_VERSION}"


def _load_cached_alignment(
    path: Path, audio_hash: str, narration_hash: str, source_audio: Path
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if (
        payload.get("audio_sha256") != audio_hash
        or payload.get("narration_sha256") != narration_hash
        or payload.get("engine_version") != _engine_version()
    ):
        return None
    if not payload.get("script_points") or float(payload.get("duration", 0.0)) <= 0:
        return None
    cached_source = str(payload.get("audio_path") or "")
    if cached_source and Path(cached_source).resolve() != source_audio.resolve():
        return None
    payload["cache_hit"] = True
    return payload


def _analyse_audio(
    audio: Path,
    narration: str,
    config: dict[str, Any],
    job: Path,
    cache_dir: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    from v3.audio_timing import analyse_alignment, probe_audio

    audio_hash = _sha256(audio)
    narration_hash = _text_sha256(narration)
    cache_path = (cache_dir or job) / f"alignment_{audio_hash[:16]}_{narration_hash[:12]}_{RUNNER_VERSION}.json"
    cached = _load_cached_alignment(cache_path, audio_hash, narration_hash, audio)
    if cached is not None:
        _json_dump(job / "alignment.json", cached)
        return cached, cache_path
    alignment_input = _alignment_audio(audio, Path(config["ffmpeg_exe"]), job)
    # Probe before Whisper so a missing/invalid audio stream fails with a useful
    # local diagnostic rather than an opaque model error.
    probe_audio(alignment_input)
    analysis = analyse_alignment(
        alignment_input,
        narration,
        Path(config["whisper_exe"]),
        Path(config["whisper_model"]),
    )
    _json_dump(job / "alignment.json", analysis)
    if not bool(analysis.get("alignment_passed")):
        raise RunnerError("真实 Whisper 逐字对齐未通过：" + "；".join(analysis.get("warnings") or []))
    analysis["audio_path"] = str(audio.resolve())
    analysis["audio_sha256"] = audio_hash
    analysis["narration_sha256"] = narration_hash
    analysis["engine_version"] = _engine_version()
    analysis["cache_hit"] = False
    _json_dump(cache_path, analysis)
    _json_dump(job / "alignment.json", analysis)
    return analysis, cache_path


def _synthetic_wav(path: Path, duration: float = 2.8) -> None:
    """Make a deterministic, non-private audio track for the smoke test."""
    sample_rate = 16000
    frame_count = int(sample_rate * duration)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        frames = bytearray()
        for index in range(frame_count):
            second = index / sample_rate
            # Three soft tones give the real renderer an actual non-silent track;
            # the timing map is explicitly synthetic rather than ASR-derived.
            frequency = (330.0, 440.0, 554.37)[min(2, int(second / max(0.01, duration / 3.0)))]
            envelope = min(1.0, second * 20.0, (duration - second) * 20.0)
            sample = int(9000 * envelope * math.sin(2.0 * math.pi * frequency * second))
            frames.extend(struct.pack("<h", sample))
        stream.writeframes(bytes(frames))


def _synthetic_analysis(audio: Path, narration: str) -> dict[str, Any]:
    from v3.audio_timing import probe_audio

    metadata = probe_audio(audio)
    visible = [index for index, char in enumerate(narration) if not char.isspace()]
    duration = float(metadata["duration"])
    points = [
        {"source_index": source_index, "time": round(duration * index / max(1, len(visible) - 1), 4)}
        for index, source_index in enumerate(visible)
    ]
    analysis = {
        "analysis_version": "smoke-1",
        **metadata,
        "audio_path": str(audio.resolve()),
        "audio_sha256": _sha256(audio),
        "narration_sha256": _text_sha256(narration),
        "speech_start": 0.0,
        "speech_end": round(duration, 3),
        "segments": [],
        "transcript": "",
        "script_points": points,
        "clauses": [],
        "alignment_score": 1.0,
        "match_ratio": 1.0,
        "script_coverage": 1.0,
        "alignment_passed": True,
        "timing_source": "synthetic_fixture",
        "engine_version": _engine_version(),
        "engine": "synthetic-smoke-fixture-not-ASR",
        "warnings": ["合成音频与人工 script_points 仅用于验证音轨封装和渲染，不代表语音识别对齐通过"],
    }
    return analysis


def _smoke_storyboard() -> tuple[dict[str, Any], dict[str, Any]]:
    narration = "Given one. Show the square. Solve it. The answer is one."
    request = {
        "title": "Offline smoke test",
        "problem": "A square has one unit.",
        "narration": narration,
        "audio_path": "smoke_audio.wav",
        "planner_mode": "model",
    }
    storyboard = {
        "schema_version": SCHEMA_VERSION,
        "planner_mode": "model",
        "title": "Offline smoke test",
        "problem": request["problem"],
        "unsupported_requirements": [],
        "entities": [{"id": "box", "kind": "square", "label": "square", "color": "#4CC9F0"}],
        "beats": [
            {
                "id": "b01",
                "layout": "equations",
                "narration": "Given one.",
                "rows": [{"text": "{{box}}＝1", "accent": False}],
                "focus": [0],
                "actions": [{"type": "show_formula", "anchor": "Given", "row": 0}],
            },
            {
                "id": "b02",
                "layout": "diagram",
                "narration": "Show the square.",
                "diagrams": [{"entity": "box", "parts": 1, "animation": "show_then_partition"}],
                "actions": [{"type": "show_whole", "anchor": "square", "entity": "box"}],
            },
            {
                "id": "b03",
                "layout": "derivation",
                "narration": "Solve it.",
                "rows": [{"text": "{{box}}＝1", "accent": False}],
                "focus": [0],
                "actions": [{"type": "focus_formula", "anchor": "Solve", "row": 0}],
            },
            {
                "id": "b04",
                "layout": "summary",
                "narration": "The answer is one.",
                "rows": [{"text": "{{box}}＝1", "accent": True}],
                "focus": "all",
                "actions": [{"type": "show_answer", "anchor": "answer", "row": 0}],
            },
        ],
    }
    request["audio_timing_summary"] = "synthetic smoke timing"
    return request, storyboard


def _normalise(raw_storyboard: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    request_for_validator = dict(request)
    request_for_validator["planner_mode"] = "model"
    request_for_validator["audio_timing_summary"] = "audio master clock"
    try:
        return normalize_storyboard(raw_storyboard, request_for_validator)
    except StoryboardValidationError as exc:
        details = getattr(exc, "errors", None) or [str(exc)]
        raise RunnerError("分镜校验失败：" + "；".join(str(item) for item in details[:20])) from exc


def _manifest_base(
    job: Path,
    quality: str,
    request_path: Path | None,
    storyboard_path: Path | None,
    job_root: Path | None = None,
) -> dict[str, Any]:
    return {
        "runner_version": RUNNER_VERSION,
        "capability_version": CAPABILITY_VERSION,
        "storyboard_schema_version": SCHEMA_VERSION,
        "engine_version": _engine_version(),
        "status": "running",
        "started_at": _now(),
        "quality": quality,
        "job_dir": str(job),
        "job_root": str(job_root or job),
        "request_path": str(request_path.resolve()) if request_path else None,
        "storyboard_path": str(storyboard_path.resolve()) if storyboard_path else None,
        "artifacts": {},
    }


def _failure(job: Path, manifest: dict[str, Any], exc: BaseException) -> None:
    manifest["status"] = "failed"
    manifest["finished_at"] = _now()
    manifest["error"] = str(exc)
    _json_dump(job / "manifest.json", manifest)
    _json_dump(job / "report.json", {"passed": False, "status": "failed", "error": str(exc), "manifest": str(job / "manifest.json")})


def _runtime_evidence(config: dict[str, Any]) -> dict[str, Any]:
    names = ("manim", "av", "PIL", "v3.capabilities", "v3.storyboard",
             "v3.audio_timing", "v3.compiler", "v3.rendering")
    modules = {name: importlib.import_module(name) for name in names}
    return {
        "sys_executable": sys.executable,
        "sys_prefix": sys.prefix,
        "sys_base_prefix": sys.base_prefix,
        "isolated": bool(sys.flags.isolated),
        "sys_path": list(sys.path),
        "manim_version": modules["manim"].__version__,
        "pyav_version": modules["av"].__version__,
        "module_files": {name: str(Path(module.__file__).resolve()) for name, module in modules.items()},
        "package_root": str(PACKAGE_ROOT),
        "engine_root": str(ENGINE_ROOT),
        "render_cwd": config["manim_project"],
        "whisper_exe": config["whisper_exe"],
        "whisper_model": config["whisper_model"],
        "ffmpeg_exe": config["ffmpeg_exe"],
        "path": os.environ.get("PATH", ""),
        "tex_on_path": shutil.which("latex"),
        "dvisvgm_on_path": shutil.which("dvisvgm"),
    }


def _run_job(
    request_path: Path,
    storyboard_path: Path,
    job: Path,
    config: dict[str, Any],
    quality: str,
    synthetic: bool = False,
    job_root: Path | None = None,
) -> dict[str, Any]:
    if not synthetic and _json_load(storyboard_path, "storyboard").get("schema_version") == "geometry-1.0":
        from geometry.pipeline import run_job
        return run_job(sys.modules[__name__], request_path, storyboard_path, job, config, quality, job_root)
    manifest = _manifest_base(job, quality, request_path, storyboard_path, job_root)
    _json_dump(job / "manifest.json", manifest)
    try:
        _json_dump(job / "runtime_evidence.json", _runtime_evidence(config))
        request, audio = _request(request_path)
        raw_storyboard = _json_load(storyboard_path, "storyboard")
        if "canvas" in raw_storyboard or "canvas" in request:
            raise RunnerError("generic/v3 does not support custom canvas or 4K; final is fixed at 1080x1440@60. Use geometry only for supported content.")
        _json_dump(job / "request.json", {**request, "audio_path": str(audio)})
        _json_dump(job / "storyboard_input.json", raw_storyboard)
        manifest["inputs"] = {
            "request_sha256": _sha256(request_path),
            "storyboard_sha256": _sha256(storyboard_path),
            "audio_sha256": _sha256(audio),
            "narration_sha256": _text_sha256(request["narration"]),
        }
        _json_dump(job / "manifest.json", manifest)
        if synthetic:
            analysis = _synthetic_analysis(audio, request["narration"])
            alignment_path = job / "alignment_synthetic_fixture.json"
            _json_dump(alignment_path, analysis)
        else:
            analysis, alignment_path = _analyse_audio(
                audio, request["narration"], config, job,
                (job_root or job) / "cache",
            )
        if not bool(analysis.get("alignment_passed")):
            raise RunnerError("音频对齐没有通过，拒绝进入渲染")
        request["audio_timing_summary"] = "audio alignment passed"
        spec = _normalise(raw_storyboard, request)
        from v3.audio_timing import apply_audio_timing
        from v3.compiler import compile_storyboard
        from v3.rendering import render_storyboard_final, render_storyboard_preview

        spec = apply_audio_timing(spec, analysis, __import__("v3.storyboard", fromlist=["estimate_motion_seconds"]).estimate_motion_seconds)
        _json_dump(job / "storyboard_normalized.json", spec)
        code, timeline = compile_storyboard(spec)
        ast.parse(code)
        code_path = job / "generated_math_video.py"
        code_path.write_text(code, encoding="utf-8")
        timeline_path = job / "timeline.json"
        _json_dump(timeline_path, {"timeline": timeline})
        preview = render_storyboard_preview(
            code,
            timeline,
            job,
            Path(config["manim_project"]),
            Path(config["python_exe"]),
        )
        if not bool(preview.get("passed")):
            raise RunnerError("低清预览验收失败；默认不绕过：" + "; ".join(str(item) for item in preview.get("issues", [])[:12]))
        if not bool(preview.get("has_audio")):
            raise RunnerError("低清预览没有音轨，拒绝报告成功")
        preview_path = Path(str(preview["preview_path"])).resolve()
        preview_copy = job / "preview.mp4"
        if preview_path != preview_copy.resolve():
            shutil.copy2(preview_path, preview_copy)
        _json_dump(job / "preview_report.json", preview)
        final: dict[str, Any] | None = None
        if quality == "final":
            final = render_storyboard_final(
                code,
                timeline,
                preview,
                Path(config["manim_project"]),
                Path(config["python_exe"]),
            )
            if not bool(final.get("passed", True)) or not bool(final.get("has_audio")):
                raise RunnerError("高清成片验收失败或缺少音轨")
            final_path = Path(str(final["final_path"])).resolve()
            final_copy = job / "final_1080x1440_60fps.mp4"
            if final_path != final_copy.resolve():
                shutil.copy2(final_path, final_copy)
            _json_dump(job / "final_report.json", final)

        manifest.update({
            "status": "passed",
            "finished_at": _now(),
            "timing_source": analysis.get("timing_source") or analysis.get("engine"),
            "cache_hit": bool(analysis.get("cache_hit", False)),
            "artifacts": {
                "request": str(job / "request.json"),
                "storyboard_input": str(job / "storyboard_input.json"),
                "storyboard_normalized": str(job / "storyboard_normalized.json"),
                "alignment": str(alignment_path),
                "code": str(code_path),
                "timeline": str(timeline_path),
                "runtime_evidence": str(job / "runtime_evidence.json"),
                "preview": str(preview_copy),
                "preview_report": str(job / "preview_report.json"),
                **({"final": str(job / "final_1080x1440_60fps.mp4"), "final_report": str(job / "final_report.json")} if final else {}),
            },
            "audio": {
                "duration": analysis.get("duration"),
                "sha256": analysis.get("audio_sha256"),
                "alignment_score": analysis.get("alignment_score"),
                "script_coverage": analysis.get("script_coverage"),
            },
        })
        report = {
            "passed": True,
            "status": "passed",
            "quality": quality,
            "timing_source": manifest["timing_source"],
            "local_validation": {
                "whisper_alignment": manifest["timing_source"] != "synthetic_fixture",
                "audio_timing_fixture": manifest["timing_source"] == "synthetic_fixture",
                "preview": True,
                "final": bool(final),
            },
            "visual_review": {"status": "not_reviewed_by_Codex", "contact_sheet": preview.get("contact_sheet_path")},
            "manifest": str(job / "manifest.json"),
            "artifacts": manifest["artifacts"],
        }
        _json_dump(job / "manifest.json", manifest)
        _json_dump(job / "report.json", report)
        return report
    except Exception as exc:  # keep a recoverable failure manifest
        _failure(job, manifest, exc)
        if isinstance(exc, RunnerError):
            raise
        raise RunnerError(str(exc)) from exc


def _contract() -> dict[str, Any]:
    from geometry.schema import contract as geometry_contract
    prompt_hash = _sha256(PROMPT_PATH) if PROMPT_PATH.is_file() else None
    prompt_text = PROMPT_PATH.read_text(encoding="utf-8") if PROMPT_PATH.is_file() else ""
    prompt_version = "director-v4" if "director-v4" in prompt_text else "unknown"
    _, storyboard_example = _smoke_storyboard()
    return {
        "runner_version": RUNNER_VERSION,
        "geometry": geometry_contract(),
        "planner": "Codex 直接产出 storyboard JSON；本 runner 不调用第三方模型/API",
        "schema_version": SCHEMA_VERSION,
        "capability_version": CAPABILITY_VERSION,
        "entity_kinds": sorted(ALLOWED_KINDS),
        "actions": sorted(ALLOWED_ACTIONS),
        "action_fields": {name: sorted(fields) for name, fields in sorted(ACTION_FIELDS.items())},
        "request_required": ["problem", "narration", "audio_path"],
        "runtime_config_required": ["python_exe", "ffmpeg_exe", "whisper_exe", "whisper_model"],
        "quality": ["preview", "final"],
        "outputs": ["manifest.json", "report.json", "storyboard_normalized.json", "generated_math_video.py", "preview.mp4"],
        "final_outputs": ["final_1080x1440_60fps.mp4", "final_report.json"],
        "director_prompt": {
            "path": str(PROMPT_PATH.relative_to(PACKAGE_ROOT)).replace("\\", "/"),
            "sha256": prompt_hash,
            "version": prompt_version,
            "use": "交给 Codex 规划分镜；不要改写逐字 narration",
        },
        "director_prompt_text": prompt_text,
        "storyboard_validation_prompt": "assets/engine/v3/storyboard.py:STORYBOARD_SYSTEM_PROMPT",
        "storyboard_system_prompt_excerpt": STORYBOARD_SYSTEM_PROMPT[:900],
        "request_example": {
            "title": "示例视频",
            "problem": "题目原文",
            "narration": "与音频逐字一致的完整旁白",
            "audio_path": "C:/input/narration.wav",
        },
        "storyboard_example": storyboard_example,
        "audio_policy": "run 必须 Whisper 本地逐字对齐；smoke 的 timing_source=synthetic_fixture，仅验证音轨渲染",
        "review_policy": "local_validation 与 visual_review 分开；runner 不把未被 Codex 审图的 contact sheet 标成 visual passed",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline Manim math-video runner")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("contract", help="输出当前本地分镜契约和能力")
    run = sub.add_parser("run", help="校验、对齐、编译并渲染用户分镜")
    run.add_argument("--request", required=True, type=Path)
    run.add_argument("--storyboard", required=True, type=Path)
    run.add_argument("--job-dir", required=True, type=Path)
    run.add_argument("--runtime-config", required=True, type=Path)
    run.add_argument("--quality", choices=("preview", "final"), default="preview")
    analyze = sub.add_parser("analyze", help="本地真实音频分析并导出绑定哈希的原始词锚点")
    analyze.add_argument("--request", required=True, type=Path)
    analyze.add_argument("--job-dir", required=True, type=Path)
    analyze.add_argument("--runtime-config", required=True, type=Path)
    smoke = sub.add_parser("smoke", help="生成合成音频和小分镜并进行真实低清渲染")
    smoke.add_argument("--job-dir", required=True, type=Path)
    smoke.add_argument("--runtime-config", required=True, type=Path)
    return parser


def _reexec_with_runtime(config: dict[str, Any], argv: list[str]) -> int | None:
    """Always use the configured isolated interpreter, even if another has Manim."""
    configured = Path(config["python_exe"]).resolve()
    current = Path(sys.executable).resolve()
    if configured == current and sys.flags.isolated:
        return None
    completed = subprocess.run(
        [str(configured), "-I", str(Path(__file__).resolve()), *argv],
        env=dict(os.environ),
    )
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "contract":
            print(json.dumps(_contract(), ensure_ascii=False, indent=2))
            return 0
        config = _runtime_config(args.runtime_config.resolve())
        delegated = _reexec_with_runtime(config, list(argv if argv is not None else sys.argv[1:]))
        if delegated is not None:
            return delegated
        job_root = _job_dir(str(args.job_dir))
        job = _new_attempt(job_root)
        if args.command == "analyze":
            from geometry.pipeline import analyze
            result = analyze(sys.modules[__name__], args.request.resolve(), job, config, job_root)
        elif args.command == "smoke":
            request_data, storyboard_data = _smoke_storyboard()
            audio = job / "smoke_audio.wav"
            _synthetic_wav(audio)
            request_data["audio_path"] = str(audio)
            request_path = job / "smoke_request.json"
            storyboard_path = job / "smoke_storyboard.json"
            _json_dump(request_path, request_data)
            _json_dump(storyboard_path, storyboard_data)
            result = _run_job(request_path, storyboard_path, job, config, "preview", synthetic=True, job_root=job_root)
        else:
            result = _run_job(args.request.resolve(), args.storyboard.resolve(), job, config, args.quality, job_root=job_root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"passed": False, "status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
