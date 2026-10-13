from __future__ import annotations

import difflib
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
from contextlib import nullcontext
from pathlib import Path
from typing import Any


TIMESTAMP_RE = re.compile(
    r"\[(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)\s+-->\s+"
    r"(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)\]\s*(.*)"
)
VISIBLE_CHAR_RE = re.compile(r"[\u3400-\u9fffA-Za-z0-9]")
DIGIT_TO_CHINESE = str.maketrans("0123456789", "零一二三四五六七八九")
CLAUSE_RE = re.compile(r"[^，。！？；;\n]+[，。！？；;]?|\n+")


def _seconds(hours: str, minutes: str, seconds: str) -> float:
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _normalise_with_indexes(text: str) -> tuple[list[str], list[int]]:
    chars: list[str] = []
    indexes: list[int] = []
    for index, raw in enumerate(str(text or "")):
        char = raw.translate(DIGIT_TO_CHINESE).lower()
        if VISIBLE_CHAR_RE.fullmatch(char):
            chars.append(char)
            indexes.append(index)
    return chars, indexes


def _normalise(text: str) -> str:
    chars, _ = _normalise_with_indexes(text)
    return "".join(chars)


def probe_audio(audio_path: Path) -> dict[str, Any]:
    try:
        import av  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Manim 环境缺少 PyAV，无法读取音频") from exc

    try:
        container = av.open(str(audio_path))
    except Exception as exc:  # noqa: BLE001 - PyAV exposes codec-specific errors
        raise ValueError(f"无法读取音频文件：{exc}") from exc
    try:
        streams = list(container.streams.audio)
        if not streams:
            raise ValueError("上传文件不包含音轨")
        stream = streams[0]
        duration = float(container.duration / av.time_base) if container.duration else 0.0
        if duration <= 0:
            duration = float(stream.duration * stream.time_base) if stream.duration else 0.0
        if duration <= 0:
            raise ValueError("无法确定音频时长")
        return {
            "duration": round(duration, 3),
            "sample_rate": int(stream.rate or 0),
            "channels": int(stream.channels or 0),
            "codec": str(stream.codec_context.name or ""),
            "bit_rate": int(stream.bit_rate or 0),
        }
    finally:
        container.close()


def _safe_asr_log(value: bytes | str | None) -> str:
    """Keep diagnostics without echoing inherited credentials."""
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else (value or "")
    for name, secret in os.environ.items():
        if len(secret) >= 8 and re.search(r"key|token|secret|password|authorization", name, re.I):
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)(bearer\s+|(?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", text)
    return re.sub(r"\bsk-[A-Za-z0-9_-]{8,}", "[REDACTED]", text)


def _token_seconds(value: Any) -> float | None:
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return round(value / 1000.0, 3)


def transcribe_segments(
    audio_path: Path,
    narration: str,
    whisper_exe: Path,
    model_path: Path,
    timeout: int = 900,
    *,
    evidence_dir: Path | None = None,
) -> list[dict[str, Any]]:
    if not whisper_exe.is_file():
        raise RuntimeError(f"没有找到本机 Whisper：{whisper_exe}")
    if not model_path.is_file():
        raise RuntimeError(f"没有找到本机中文语音模型：{model_path}")
    if evidence_dir is not None:
        evidence_dir = Path(evidence_dir)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        workspace = nullcontext(tempfile.mkdtemp(prefix="whisper_", dir=evidence_dir))
    else:
        workspace = tempfile.TemporaryDirectory(prefix="manim_audio_align_")
    with workspace as temporary:
        output_base = Path(temporary) / "alignment"
        command = [
            str(whisper_exe),
            "-m", str(model_path),
            "-f", str(audio_path),
            "-l", "zh",
            "-ml", "28",
            "-sow",
            "-t", "8",
            "-np",
            "-ojf",
            "-of", str(output_base),
        ]
        prompt = re.sub(r"\s+", "", narration).strip()
        if prompt:
            command.extend(["--prompt", prompt[:800], "--carry-initial-prompt"])
        completed = None
        stdout = stderr = ""
        process_error = None
        try:
            completed = subprocess.run(
                command, cwd=str(whisper_exe.parent), capture_output=True,
                timeout=timeout, check=False,
            )
            stdout = _safe_asr_log(completed.stdout)
            stderr = _safe_asr_log(completed.stderr)
        except (subprocess.TimeoutExpired, OSError) as exc:
            process_error = type(exc).__name__
            stdout = _safe_asr_log(getattr(exc, "stdout", None))
            stderr = _safe_asr_log(getattr(exc, "stderr", None))
            raise RuntimeError(f"Local Whisper {process_error}; inspect retained evidence") from None
        finally:
            if evidence_dir is not None:
                folder = Path(temporary)
                (folder / "stdout.log").write_text(stdout, encoding="utf-8")
                (folder / "stderr.log").write_text(stderr, encoding="utf-8")
                artifacts = [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                             for p in (output_base.with_suffix(".json"), folder / "stdout.log", folder / "stderr.log") if p.is_file()]
                (folder / "evidence_manifest.json").write_text(json.dumps({
                    "source": "whisper.cpp local CLI", "logs_redacted": True,
                    "returncode": completed.returncode if completed is not None else None,
                    "process_error": process_error, "artifacts": artifacts,
                }, ensure_ascii=False, indent=2), encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError("本机 Whisper 对齐失败：" + (stderr or stdout)[-3000:])
        full_json = output_base.with_suffix(".json")
        if full_json.is_file():
            try:
                payload = json.loads(full_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            segments: list[dict[str, Any]] = []
            for item in payload.get("transcription", []) if isinstance(payload, dict) else []:
                offsets = item.get("offsets") or {}
                start = _token_seconds(offsets.get("from"))
                end = _token_seconds(offsets.get("to"))
                text = str(item.get("text", "")).strip()
                tokens: list[dict[str, Any]] = []
                for token in item.get("tokens") or []:
                    token_text = str(token.get("text", ""))
                    if token_text.startswith("[_") or not token_text.strip() or (evidence_dir is None and not _normalise(token_text)):
                        continue
                    token_offsets = token.get("offsets") or {}
                    tokens.append({
                        "text": token_text,
                        "start": _token_seconds(token_offsets.get("from")),
                        "end": _token_seconds(token_offsets.get("to")),
                        "raw_token": token,
                    })
                if (text and start is not None and end is not None and end > start) or (evidence_dir is not None and tokens):
                    segments.append({"start": start, "end": end, "text": text, "tokens": tokens})
            if segments:
                return segments

    segments = []
    for line in stdout.splitlines():
        match = TIMESTAMP_RE.search(line.strip())
        if not match:
            continue
        start = _seconds(match.group(1), match.group(2), match.group(3))
        end = _seconds(match.group(4), match.group(5), match.group(6))
        text = match.group(7).strip()
        if text and end > start:
            segments.append({"start": round(start, 3), "end": round(end, 3), "text": text})
    if not segments:
        raise RuntimeError("本机 Whisper 没有识别出带时间戳的语音段")
    return segments


def _asr_character_timeline(segments: list[dict[str, Any]]) -> tuple[list[str], list[float]]:
    chars: list[str] = []
    times: list[float] = []
    for segment in segments:
        token_items = list(segment.get("tokens") or [])
        usable_tokens = [item for item in token_items if _normalise(item.get("text", ""))]
        if usable_tokens:
            for token in usable_tokens:
                normalised = list(_normalise(token.get("text", "")))
                start = float(token.get("start", segment.get("start", 0.0)))
                end = max(start + 0.012 * len(normalised), float(token.get("end", start)))
                width = (end - start) / max(1, len(normalised))
                for index, char in enumerate(normalised):
                    chars.append(char)
                    times.append(start + width * (index + 0.5))
            continue
        normalised = list(_normalise(segment.get("text", "")))
        if not normalised:
            continue
        start = float(segment.get("start", 0.0))
        end = max(start + 0.02, float(segment.get("end", start + 0.02)))
        width = (end - start) / len(normalised)
        for index, char in enumerate(normalised):
            chars.append(char)
            times.append(start + width * (index + 0.5))
    return chars, times


def _interpolated_script_times(
    script_chars: list[str],
    asr_chars: list[str],
    asr_times: list[float],
    speech_start: float,
    speech_end: float,
) -> tuple[list[float], dict[str, Any]]:
    if not script_chars:
        return [], {"ratio": 0.0, "coverage": 0.0, "matched": 0, "last_matched_time": 0.0}
    matcher = difflib.SequenceMatcher(None, script_chars, asr_chars, autojunk=False)
    matched: dict[int, float] = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            script_index = block.a + offset
            asr_index = block.b + offset
            if 0 <= asr_index < len(asr_times):
                matched[script_index] = asr_times[asr_index]

    anchors = [(-1, speech_start)]
    anchors.extend(sorted(matched.items()))
    anchors.append((len(script_chars), speech_end))
    result = [speech_start] * len(script_chars)
    for anchor_index in range(len(anchors) - 1):
        left_index, left_time = anchors[anchor_index]
        right_index, right_time = anchors[anchor_index + 1]
        span = right_index - left_index
        if span <= 0:
            continue
        right_time = max(left_time, right_time)
        for script_index in range(left_index + 1, min(right_index, len(script_chars))):
            fraction = (script_index - left_index) / span
            result[script_index] = left_time + (right_time - left_time) * fraction
        if 0 <= right_index < len(script_chars):
            result[right_index] = right_time
    for index in range(1, len(result)):
        result[index] = max(result[index], result[index - 1] + 0.001)

    matched_times = list(matched.values())
    quality = {
        "ratio": round(matcher.ratio(), 4),
        "coverage": round(len(matched) / max(1, len(script_chars)), 4),
        "matched": len(matched),
        "last_matched_time": round(max(matched_times) if matched_times else 0.0, 3),
        "first_matched_time": round(min(matched_times) if matched_times else 0.0, 3),
    }
    return result, quality


def _script_clauses(narration: str, source_indexes: list[int], times: list[float]) -> list[dict[str, Any]]:
    if not source_indexes or not times:
        return []
    clauses: list[dict[str, Any]] = []
    for match in CLAUSE_RE.finditer(narration):
        text = match.group(0).strip()
        if not _normalise(text):
            continue
        positions = [
            index for index, source_index in enumerate(source_indexes)
            if match.start() <= source_index < match.end()
        ]
        if not positions:
            continue
        start_pos = positions[0]
        end_pos = positions[-1]
        next_time = times[min(len(times) - 1, end_pos + 1)]
        clauses.append({
            "text": text,
            "source_start": match.start(),
            "source_end": match.end(),
            "start": round(max(0.0, times[start_pos] - 0.08), 2),
            "end": round(max(times[end_pos] + 0.08, next_time), 2),
        })
    return clauses


def analyse_alignment(
    audio_path: Path,
    narration: str,
    whisper_exe: Path,
    model_path: Path,
) -> dict[str, Any]:
    narration = str(narration or "").strip()
    if len(_normalise(narration)) < 4:
        raise ValueError("逐字旁白过短，无法与音频对齐")
    metadata = probe_audio(audio_path)
    segments = transcribe_segments(audio_path, narration, whisper_exe, model_path)
    script_chars, source_indexes = _normalise_with_indexes(narration)
    asr_chars, asr_times = _asr_character_timeline(segments)
    speech_start = float(segments[0]["start"])
    speech_end = float(segments[-1]["end"])
    script_times, quality = _interpolated_script_times(
        script_chars, asr_chars, asr_times, speech_start, speech_end
    )
    score = round(0.55 * quality["ratio"] + 0.45 * quality["coverage"], 3)
    warnings: list[str] = []
    if score < 0.62:
        warnings.append("音频与逐字文案的一致度偏低，请检查是否传错音频、漏句或多句")
    trailing_unmatched = max(0.0, speech_end - float(quality.get("last_matched_time", 0.0)))
    if quality.get("matched", 0) and trailing_unmatched > 1.5:
        warnings.append(f"音频末尾约有 {trailing_unmatched:.1f} 秒语音未在文案中可靠匹配，可能存在多余口播")
    leading_unmatched = max(0.0, float(quality.get("first_matched_time", 0.0)) - speech_start)
    if quality.get("matched", 0) and leading_unmatched > 1.2:
        warnings.append(f"音频开头约有 {leading_unmatched:.1f} 秒语音未在文案中可靠匹配")
    alignment_passed = (
        score >= 0.62
        and float(quality.get("coverage", 0.0)) >= 0.58
        and trailing_unmatched <= 1.5
        and leading_unmatched <= 1.2
    )

    points = [
        {"source_index": source_index, "time": round(script_times[index], 4)}
        for index, source_index in enumerate(source_indexes)
    ]
    transcript = "".join(segment["text"] for segment in segments)
    return {
        "analysis_version": "2.2",
        **metadata,
        "audio_path": str(audio_path.resolve()),
        "audio_sha256": hashlib.sha256(audio_path.read_bytes()).hexdigest(),
        "narration_sha256": hashlib.sha256(narration.encode("utf-8")).hexdigest(),
        "speech_start": round(speech_start, 3),
        "speech_end": round(speech_end, 3),
        "segments": segments,
        "transcript": transcript,
        "script_points": points,
        "clauses": _script_clauses(narration, source_indexes, script_times),
        "alignment_score": score,
        "match_ratio": quality["ratio"],
        "script_coverage": quality["coverage"],
        "leading_unmatched_seconds": round(leading_unmatched, 3),
        "trailing_unmatched_seconds": round(trailing_unmatched, 3),
        "alignment_passed": alignment_passed,
        "warnings": warnings,
        "engine": "whisper.cpp-small-local-token-timestamps",
    }


def _compact_source(text: str) -> tuple[str, list[int]]:
    chars, indexes = _normalise_with_indexes(text)
    return "".join(chars), indexes


def _locate_excerpt(excerpt: str, narration: str, cursor: int) -> tuple[int, int] | None:
    compact_source, source_indexes = _compact_source(narration)
    compact_excerpt = _normalise(excerpt)
    if not compact_excerpt:
        return None
    compact_cursor = 0
    while compact_cursor < len(source_indexes) and source_indexes[compact_cursor] < cursor:
        compact_cursor += 1
    found = compact_source.find(compact_excerpt, compact_cursor)
    if found < 0:
        found = compact_source.find(compact_excerpt)
    if found < 0:
        return None
    start = source_indexes[found]
    end = source_indexes[found + len(compact_excerpt) - 1] + 1
    return start, end


def _time_for_source(points: list[dict[str, Any]], source_index: int, duration: float) -> float:
    if not points:
        return duration * 0.5
    if source_index <= int(points[0]["source_index"]):
        return float(points[0]["time"])
    if source_index >= int(points[-1]["source_index"]):
        return float(points[-1]["time"])
    left = points[0]
    for right in points[1:]:
        if int(right["source_index"]) >= source_index:
            left_index = int(left["source_index"])
            right_index = int(right["source_index"])
            fraction = (source_index - left_index) / max(1, right_index - left_index)
            return float(left["time"]) + (float(right["time"]) - float(left["time"])) * fraction
        left = right
    return float(points[-1]["time"])


def _locate_anchor_within(
    anchor: str,
    narration: str,
    beat_range: tuple[int, int] | None,
    anchor_offset: int | None = None,
) -> tuple[int, int] | None:
    """Locate an exact action phrase inside its already-locked narration beat."""
    if not beat_range or not anchor:
        return None
    beat_start, beat_end = beat_range
    source_slice = narration[beat_start:beat_end]
    if anchor_offset is not None and 0 <= anchor_offset < len(source_slice):
        candidate_end = anchor_offset + len(anchor)
        if source_slice[anchor_offset:candidate_end] == anchor:
            return beat_start + anchor_offset, beat_start + candidate_end
    direct = source_slice.find(anchor)
    if direct >= 0:
        return beat_start + direct, beat_start + direct + len(anchor)
    compact_source, source_indexes = _compact_source(source_slice)
    compact_anchor = _normalise(anchor)
    found = compact_source.find(compact_anchor)
    if found < 0 or not compact_anchor:
        return None
    start = beat_start + source_indexes[found]
    end = beat_start + source_indexes[found + len(compact_anchor) - 1] + 1
    return start, end


def apply_audio_timing(
    spec: dict[str, Any],
    analysis: dict[str, Any],
    estimate_motion_seconds: Any,
    tail_hold: float = 2.0,
) -> dict[str, Any]:
    """Make the uploaded audio the hard master clock for all storyboard beats."""
    narration = str(spec.get("narration", ""))
    expected_hash = hashlib.sha256(narration.encode("utf-8")).hexdigest()
    if analysis.get("narration_sha256") != expected_hash:
        raise ValueError("音频分析对应的逐字文案已经变化，请重新分析音频")
    beats = list(spec.get("beats") or [])
    if not beats:
        raise ValueError("没有可与音频对齐的分镜")
    duration = float(analysis.get("duration", 0.0))
    if duration <= 0:
        raise ValueError("音频时长无效")
    points = list(analysis.get("script_points") or [])

    ranges: list[tuple[int, int] | None] = []
    source_cursor = 0
    for beat in beats:
        located = _locate_excerpt(str(beat.get("narration", "")), narration, source_cursor)
        ranges.append(located)
        if located:
            source_cursor = max(source_cursor, located[1])

    timed_ranges: list[tuple[float, float] | None] = []
    for located in ranges:
        if not located:
            timed_ranges.append(None)
            continue
        start, end = located
        first = _time_for_source(points, start, duration)
        last = _time_for_source(points, max(start, end - 1), duration)
        timed_ranges.append((first, max(first, last)))

    silent_tail = beats[-1].get("layout") == "summary" and not str(beats[-1].get("narration", "")).strip()
    spoken_ranges = timed_ranges[:-1] if silent_tail else timed_ranges
    if spoken_ranges and all(value is not None for value in spoken_ranges):
        concrete = [value for value in spoken_ranges if value is not None]
        boundaries = [0.0]
        for index in range(len(concrete) - 1):
            # Split the pause exactly between the last spoken character of the
            # current beat and the first character of the next beat. Using the
            # midpoint of whole sentences makes a long sentence steal time
            # from a short neighbour and visibly desynchronises the motion.
            current_end = concrete[index][1]
            next_start = concrete[index + 1][0]
            boundaries.append((current_end + max(current_end, next_start)) / 2.0)
        boundaries.append(duration)
    else:
        # Defensive fallback for a malformed third-party storyboard. Normal
        # audio mode requires verbatim complete coverage, so this should be
        # rare, but proportional timing remains deterministic and renderable.
        spoken_count = len(beats) - int(silent_tail)
        boundaries = [duration * index / spoken_count for index in range(spoken_count + 1)]

    if silent_tail:
        boundaries.append(duration + max(0.5, min(5.0, float(tail_hold))))

    minimum_gap = min(0.12, duration / max(1, len(beats)) * 0.45)
    for index in range(1, len(boundaries) - 1):
        boundaries[index] = max(boundaries[index], boundaries[index - 1] + minimum_gap)
    for index in range(len(boundaries) - 2, 0, -1):
        boundaries[index] = min(boundaries[index], boundaries[index + 1] - minimum_gap)

    dense: list[str] = []
    entities = list(spec.get("entities") or [])
    for index, beat in enumerate(beats):
        start = max(0.0, boundaries[index])
        limit = boundaries[-1] if silent_tail and index == len(beats) - 1 else duration
        end = min(limit, max(start + minimum_gap, boundaries[index + 1]))
        available = max(minimum_gap, end - start)
        planned = max(0.1, float(estimate_motion_seconds(beat, entities, index, include_hold=False)))
        scale = min(1.0, max(0.16, (available - 0.04) / planned))
        if scale < 0.42:
            dense.append(str(beat.get("id", f"b{index + 1:02d}")))
        beat["audio_start"] = round(start, 3)
        beat["audio_end"] = round(end, 3)
        beat["duration"] = round(available, 3)
        beat["motion_scale"] = round(scale, 4)

        anchored_actions = 0
        located_beat = ranges[index]
        actions = list(beat.get("actions") or [])
        for action_index, action in enumerate(actions):
            located_action = _locate_anchor_within(
                str(action.get("anchor", "")),
                narration,
                located_beat,
                int(action.get("anchor_offset", -1)),
            )
            if located_action:
                action_source_start, action_source_end = located_action
                action_start = _time_for_source(points, action_source_start, duration) - 0.05
                action_end = _time_for_source(
                    points, max(action_source_start, action_source_end - 1), duration
                ) + 0.05
                action["source_start"] = action_source_start
                action["source_end"] = action_source_end
                action["audio_start"] = round(max(start, min(end - 0.04, action_start)), 3)
                action["audio_end"] = round(max(action["audio_start"] + 0.04, min(end, action_end)), 3)
                anchored_actions += 1
            else:
                if silent_tail and index == len(beats) - 1:
                    action["audio_start"] = round(start, 3)
                    action["audio_end"] = round(min(end, start + 0.24), 3)
                    continue
                # This is a defensive path for imported third-party specs. The
                # local normalizer normally rejects or repairs such anchors.
                ratio = (action_index + 0.5) / max(1, len(actions))
                fallback = start + available * ratio
                action["audio_start"] = round(min(end - 0.04, fallback), 3)
                action["audio_end"] = round(min(end, fallback + 0.08), 3)
        beat["word_action_count"] = anchored_actions

    warnings = list(analysis.get("warnings") or [])
    if dense:
        warnings.append("以下分镜语速较快，已自动压缩动画节奏：" + "、".join(dense))
    spec["audio"] = {
        "path": str(analysis.get("audio_path", "")),
        "duration": round(duration, 3),
        "speech_start": float(analysis.get("speech_start", 0.0)),
        "speech_end": float(analysis.get("speech_end", duration)),
        "tail_hold": round(max(0.5, min(5.0, float(tail_hold))), 2),
        "alignment_score": float(analysis.get("alignment_score", 0.0)),
        "script_coverage": float(analysis.get("script_coverage", 0.0)),
        "engine": str(analysis.get("engine", "")),
        "word_sync": "exact_phrase_anchors",
        "word_action_count": sum(int(beat.get("word_action_count", 0)) for beat in beats),
        "warnings": warnings,
    }
    return spec


def alignment_prompt_summary(analysis: dict[str, Any]) -> str:
    clauses = list(analysis.get("clauses") or [])
    lines = [
        f"音频总时长：{float(analysis.get('duration', 0.0)):.2f} 秒。",
        "音频是唯一主时间轴；duration 仅作占位，最终由本机覆盖。",
        "请按下面时间顺序切分 beats；每个 beat 的 narration 必须是逐字文案中的连续原文。",
        "每个可见变化都必须提供 actions.anchor，anchor 必须逐字来自对应 narration 中真正触发该动作的词组。",
    ]
    for item in clauses[:80]:
        lines.append(f"[{float(item['start']):.2f}-{float(item['end']):.2f}] {item['text']}")
    return "\n".join(lines)


def compact_public_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in analysis.items()
        if key not in {"script_points"}
    }


def save_analysis(path: Path, analysis: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")


def load_analysis(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("音频分析文件损坏")
    return value
