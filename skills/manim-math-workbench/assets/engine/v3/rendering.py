from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from .equation_motion import equation_motion_tokens
from .partial_cache import retain_config, partial_index


def _console_python(python_exe: Path) -> Path:
    if python_exe.name.lower() == "pythonw.exe":
        candidate = python_exe.with_name("python.exe")
        if candidate.is_file():
            return candidate
    return python_exe


def _render_output_text(value: Any) -> str:
    # TimeoutExpired can contain bytes even when run(text=True) was requested.
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _redact_render_detail(value: str) -> str:
    """Sanitize UI diagnostics without altering the complete local log."""
    text = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", value)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"\bsk-[A-Za-z0-9._~+/=\-]{8,}", "[已隐藏密钥]", text)
    text = re.sub(r"(?i)\bBearer\s+[^\s\"'<>]+", "Bearer [已隐藏密钥]", text)
    text = re.sub(
        r"(?i)([\"']?(?:api[_-]?key|access[_-]?token|authorization|password|secret)[\"']?\s*[:=]\s*)"
        r"(?:\"[^\"]*\"|'[^']*'|[^\s,;&}\]]+)",
        lambda match: match[1] + "[已隐藏密钥]", text,
    )
    text = re.sub(r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@", r"\1[已隐藏凭据]@", text)
    text = re.sub(r"(?i)([?&](?:key|token|api_key|access_token|signature)=)[^\s&#\"']+",
                  r"\1[已隐藏密钥]", text)
    return text


def _render_failure_summary(stdout: Any, stderr: Any, log_path: Path | None = None,
                            limit: int = 1100) -> str:
    """Put the actual exception first, before any downstream message truncation.

    Manim Rich tracebacks wrap long Windows file paths across bordered lines.
    Looking at the start of a 6000-character traceback hides its final error;
    looking only at stderr also misses exceptions printed on stdout.
    """
    limit = max(120, min(int(limit), 1100))
    streams = []
    for raw in (stderr, stdout):
        clean = _redact_render_detail(_render_output_text(raw)).replace("\r\n", "\n").replace("\r", "\n")
        streams.append([line.strip().strip("│┃║| ").strip() for line in clean.splitlines()])
    exception_re = re.compile(
        r"^(?:(?:[A-Za-z_]\w*\.)*(?:[A-Za-z_]\w*(?:Error|Exception|Interrupt|Exit)|Error|Exception|"
        r"TimeoutExpired|ExceptionGroup|BaseExceptionGroup|StopIteration|StopAsyncIteration))"
        r"(?::.*)?$"
    )
    chosen = None
    for lines in streams:
        hits = [index for index, line in enumerate(lines) if exception_re.fullmatch(line)]
        if hits:
            chosen = (lines, hits[-1])
            break
    locations: list[str] = []
    if chosen is not None:
        lines, error_index = chosen
        details = [lines[error_index]]
        for following in lines[error_index + 1:error_index + 4]:
            if (not following or "Traceback" in following or
                    re.match(r"^[+─━└┌╭╰][-─━+┘┐╮╯]+$", following)):
                break
            details.append(following)
        headline = " ".join(details)
        for index, line in enumerate(lines[:error_index]):
            standard = re.search(r'File [\"\']([^\"\']+)[\"\'], line (\d+)(?:, in ([\w.<>]+))?', line)
            if standard:
                path, number, function = standard.groups()
                locations.append(f"{path}:{number}" + (f" in {function}" if function else ""))
                continue
            if not re.match(r"^(?:[A-Za-z]:[\\/]|/)", line):
                continue
            joined = line
            for extra in lines[index + 1:min(index + 4, error_index)]:
                if re.search(r"\.pyw?:\d+\s+in\s+\S+", joined):
                    break
                joined += (" " if re.search(r"\.pyw?:\d+(?:\s+in)?$", joined) else "") + extra
            rich = re.match(r"^(.+?\.pyw?):(\d+)(?:\s+in\s+([\w.<>]+))?", joined)
            if rich:
                path, number, function = rich.groups()
                locations.append(f"{path}:{number}" + (f" in {function}" if function else ""))
    else:
        useful = [line for line in (streams[0] or streams[1]) if line and
                  not re.fullmatch(r"[+\-─━│| ╭╰╮╯]+", line)]
        errors = []
        for lines in streams:
            errors = [line for line in lines if re.search(r"(?i)error|failed|failure|拒绝|失败|错误", line)]
            if errors:
                break
        headline = "；".join((errors or useful)[-3:]) or "渲染进程失败，但没有返回错误详情"

    def shorten(text: str, budget: int) -> str:
        if len(text) <= budget:
            return text
        if budget < 12:
            return text[:budget]
        tail = min(100, budget // 3)
        return text[:budget - tail - 1] + "…" + text[-tail:]

    headline = shorten(headline, min(440, limit // 2))
    footer = "\n完整日志：" + shorten(_redact_render_detail(str(log_path)), min(260, limit // 3)) if log_path else ""
    budget = limit - len(headline) - len(footer)
    if locations and budget > 8:
        # The failing frame is more useful than its parent if space is limited.
        unique = list(dict.fromkeys(reversed(locations)))[:2]
        context = "\n定位：" + shorten("；".join(unique), budget - 4)
    else:
        context = ""
    return (headline + context + footer)[:limit]


def _run_render(command: list[str], cwd: Path, timeout: int, log_path: Path,
                failure_label: str) -> subprocess.CompletedProcess[str]:
    """Keep all child output on disk and share one safe failure path for both qualities."""
    # The parent's decoder does not configure a Windows child's pipe encoding.
    # Force matching UTF-8 streams without changing the server's environment.
    child_env = os.environ.copy()
    child_env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    log_path.with_suffix(".command.json").write_text(
        json.dumps({"command": command, "cwd": str(cwd)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        completed = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=timeout, check=False,
                                   env=child_env)
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = _render_output_text(exc.stdout), _render_output_text(exc.stderr)
        detail = f"TimeoutExpired: 渲染超过 {timeout} 秒，进程已超时"
        log_path.write_text(stdout + "\n" + stderr + "\n" + detail, encoding="utf-8")
        raise RuntimeError(failure_label + _render_failure_summary(stdout, stderr + "\n" + detail, log_path)) from exc
    except OSError as exc:
        detail = f"{type(exc).__name__}: {exc}"
        log_path.write_text(detail, encoding="utf-8")
        raise RuntimeError(failure_label + _render_failure_summary("", detail, log_path)) from exc
    log_path.write_text(_render_output_text(completed.stdout) + "\n" + _render_output_text(completed.stderr), encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(failure_label + _render_failure_summary(completed.stdout, completed.stderr, log_path))
    return completed


def _measured_stable_times(output: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for match in re.finditer(r"STUDIO_STABLE (\{[^\r\n]+\})", output):
        try:
            record = json.loads(match[1])
            value = float(record["time"])
            if isinstance(record.get("id"), str) and math.isfinite(value) and value >= 0:
                result[record["id"]] = value
        except (ValueError, TypeError, KeyError):
            continue
    return result


def _measured_layouts(output: str) -> list[dict[str, Any]]:
    """Read completed layout changes, never assume a diagram starts in its final slot."""
    records: list[dict[str, Any]] = []
    for match in re.finditer(r"STUDIO_LAYOUT (\{[^\r\n]+\})", output):
        try:
            record = json.loads(match[1])
            moment = float(record["time"])
            centers = record["centers"]
            if not math.isfinite(moment) or moment < 0 or not isinstance(centers, dict):
                continue
            clean_centers = {}
            for key, center in centers.items():
                if not isinstance(key, str) or not isinstance(center, list) or len(center) != 3:
                    continue
                values = [float(value) for value in center]
                if all(math.isfinite(value) for value in values):
                    clean_centers[key] = values
            records.append({"time": moment, "centers": clean_centers})
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
    return sorted(records, key=lambda item: item["time"])


def _measured_geometry_times(output: str) -> dict[tuple[str, str, int, str], float]:
    """Use the renderer's completed semantic action times for geometry snapshots."""
    records: dict[tuple[str, str, int, str], float] = {}
    for match in re.finditer(r"STUDIO_GEOMETRY (\{[^\r\n]+\})", output):
        try:
            record = json.loads(match[1])
            moment = float(record["time"])
            stage = record["stage"]
            instance = int(record.get("instance", 0))
            if not math.isfinite(moment) or moment < 0 or instance < 0:
                continue
            if stage not in {"whole", "partitioned", "extracted", "diagram_focus"}:
                continue
            if not isinstance(record.get("id"), str) or not isinstance(record.get("entity"), str):
                continue
            records[(record["id"], record["entity"], instance, stage)] = moment
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
    return records


def _with_measured_center(target: dict[str, Any], layouts: list[dict[str, Any]]) -> dict[str, Any]:
    """Annotate a snapshot with the latest visible-layout position at that instant."""
    key = f"{target.get('entity', '')}@{int(target.get('instance', 0))}"
    moment = float(target.get("time", 0.0))
    for record in reversed(layouts):
        if float(record["time"]) > moment + 1e-6:
            continue
        center = record["centers"].get(key)
        # Each layout record is a full state: do not resurrect a removed diagram
        # from an older record just because its key is absent in the latest one.
        if center is not None:
            return {**target, "center": list(center), "position_source": "renderer"}
        break
    return target


def _formula_action_report(output: str, timeline: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Require an actual, ordered execution receipt for every queued action."""
    records, issues = [], []
    for match in re.finditer(r"STUDIO_FORMULA_ACTION (\{[^\r\n]+\})", output):
        try:
            record = json.loads(match[1])
            if isinstance(record, dict):
                records.append(record)
        except ValueError:
            issues.append({"category": "formula_motion", "problem": "公式动效执行记录无法解析"})
    active_tokens = None
    for event in timeline:
        if not event.get("formula_queue"):
            continue
        actual = [r for r in records if r.get("id") == event.get("id")]
        expected = list(enumerate(event.get("actions", [])))
        previous = -1.0
        for index, action in expected:
            target = equation_motion_tokens(action["target_text"]) if action.get("target_text") else None
            expected_effect = None
            if active_tokens and target and target.count("＝") == active_tokens.count("＝") == 1:
                old_left = active_tokens[:active_tokens.index("＝") + 1]
                new_left = target[:target.index("＝") + 1]
                if action.get("type") in {"transform_formula", "show_answer"} and old_left == new_left:
                    expected_effect = "rhs_update"
                elif action.get("type") in {"transform_formula", "substitute", "combine"}:
                    expected_effect = "continuous_terms"
            found = [r for r in actual if r.get("index") == index]
            valid = len(found) == 1 and found[0].get("type") == action.get("type") and found[0].get("anchor") == action.get("anchor")
            if not valid:
                issues.append({"frame": event.get("id"), "category": "formula_motion",
                    "problem": f"公式动作{index + 1}没有唯一且匹配的实际执行记录"})
            elif expected_effect and found[0].get("effect") != expected_effect:
                issues.append({"frame": event.get("id"), "category": "formula_motion",
                    "problem": f"公式动作{index + 1}未执行预期的{expected_effect}，不能用整式重画替代"})
            elif action.get("type") in {"copy_equation", "merge_equations"} or found[0].get("effect") in {"rhs_update", "continuous_terms"}:
                motion = found[0].get("motion") or {}
                if not isinstance(motion, dict):
                    motion = {}
                before, after = motion.get("before_sizes", []), motion.get("after_sizes", [])
                try:
                    unchanged = bool(before) and len(before) == len(after) and all(
                        len(a) == len(b) == 2 and all(math.isfinite(float(x)) and math.isfinite(float(y)) and float(x) > 0 and float(y) > 0
                            and math.isclose(float(x), float(y), rel_tol=1e-7, abs_tol=1e-7)
                            for x, y in zip(a, b)) for a, b in zip(before, after))
                    if action["type"] == "copy_equation":
                        correct = motion.get("source_stationary") is True and motion.get("distinct_copy") is True \
                            and float(motion.get("moved", 0)) > 0.2 and motion.get("source_row") == action.get("source_row") \
                            and motion.get("slot") == action.get("slot")
                    elif action["type"] == "merge_equations":
                        correct = motion.get("reused_tokens") is True and motion.get("removed_equals") == 1 \
                            and motion.get("entities_before") == motion.get("entities_after") \
                            and motion.get("slots") == action.get("slots") and int(motion.get("moved_count", 0)) > 0
                    elif found[0].get("effect") == "rhs_update":
                        correct = (motion.get("left_stationary") is True and motion.get("left_ids_preserved") is True
                            and motion.get("before_tokens") == motion.get("after_left_tokens")
                            and motion.get("left_count") == len(before) == len(motion.get("before_tokens", [])))
                        if target and active_tokens:
                            correct = correct and motion["before_tokens"] == old_left and motion["after_left_tokens"] == new_left
                    else:
                        old, new = motion.get("before_tokens", []), motion.get("after_tokens", [])
                        old_ids, new_ids = motion.get("before_ids", []), motion.get("after_ids", [])
                        available, reuse_pairs = list(range(len(old))), []
                        for j, token in enumerate(new):
                            i = next((i for i in available if old[i] == token), None)
                            if i is not None:
                                available.remove(i)
                                reuse_pairs.append((i, j))
                        correct = (len(old) == len(old_ids) == len(set(old_ids))
                            and len(new) == len(new_ids) == len(set(new_ids))
                            and len(reuse_pairs) == motion.get("reused_count") == len(before)
                            and len(new) - len(reuse_pairs) == motion.get("created_count")
                            and len(available) == motion.get("removed_count")
                            and all(old_ids[i] == new_ids[j] for i, j in reuse_pairs)
                            and len(set(old_ids) & set(new_ids)) == len(reuse_pairs))
                        if target and active_tokens:
                            correct = correct and old == active_tokens and new == target
                except (TypeError, ValueError, IndexError, KeyError):
                    correct, unchanged = False, False
                if not correct or not unchanged:
                    issues.append({"frame": event.get("id"), "category": "formula_motion",
                                   "problem": "公式搬运/更新未保留原式、词项数量、对象身份或尺寸"})
            if action.get("type") == "merge_equations" or expected_effect:
                active_tokens = target
            elif action.get("type") in {"clear_work", "show_text", "show_formula", "show_answer"}:
                active_tokens = None
        for record in actual:
            try:
                start, end = float(record["start"]), float(record["end"])
            except (KeyError, TypeError, ValueError):
                start, end = float("nan"), float("nan")
            if not math.isfinite(start) or not math.isfinite(end) or start < 0 or start < previous - 0.001 or end < start:
                issues.append({"frame": event.get("id"), "category": "formula_motion", "problem": "连续公式动作时序错误"})
            previous = end
        if len(actual) != len(expected):
            issues.append({"frame": event.get("id"), "category": "formula_motion", "problem": "公式实际动作数量与分镜不一致"})
    return records, issues


def _motion_report(output: str, timeline: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Check actual collection counts and dimensions, not a model's self-review."""
    records = []
    issues = []
    for match in re.finditer(r"STUDIO_MOTION (\{[^\r\n]+\})", output):
        try:
            record = json.loads(match[1])
            if isinstance(record, dict):
                records.append(record)
        except ValueError:
            issues.append({"category": "part_motion", "problem": "动效执行记录无法解析"})
    for event in timeline:
        expected = [a for a in event.get("actions", []) if a.get("type") in {"collect_parts", "focus_part"}]
        actual = [r for r in records if r.get("id") == event.get("id")]
        for action in expected:
            match = next((r for r in actual if r.get("action") == action["type"]), None)
            if match is None:
                issues.append({"frame": event.get("id"), "category": "part_motion", "problem": f"{action['type']}没有实际执行记录"})
                continue
            actual.remove(match)
            if action["type"] != "collect_parts":
                continue
            before, after = match.get("before_sizes", []), match.get("after_sizes", [])
            count = match.get("count", 0)
            if not count or len(before) != count or len(after) != count or (action.get("count") and count != action["count"]):
                issues.append({"frame": event.get("id"), "category": "part_motion", "problem": "汇集等份的实际数量与分镜不符"})
            if action.get("total") and str(match.get("total")) != str(action["total"]):
                issues.append({"frame": event.get("id"), "category": "part_motion", "problem": "汇集总数与分镜不符"})
            try:
                unchanged = all(len(b) == len(a) == 2 and all(
                    math.isfinite(float(x)) and math.isfinite(float(y)) and float(x) > 0
                    and math.isclose(float(x), float(y), abs_tol=1e-7, rel_tol=1e-7)
                    for x, y in zip(b, a)) for b, a in zip(before, after))
            except (TypeError, ValueError):
                unchanged = False
            if not unchanged:
                issues.append({"frame": event.get("id"), "category": "part_motion", "problem": "汇集前后等份尺寸发生变化"})
    return records, issues


def _select_targets(
    timeline: list[dict[str, Any]],
    measured: dict[str, float] | None = None,
    geometry_times: dict[tuple[str, str, int, str], float] | None = None,
    layouts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    measured = measured or {}
    geometry_times = geometry_times or {}
    layouts = layouts or []
    targets: list[dict[str, Any]] = [{"id": "title", "layout": "title", "time": 0.68, "expected": "标题稳定出现"}]
    for event in timeline:
        for checkpoint in event.get("checkpoints") or []:
            geometry_key = (
                str(event.get("id", "")), str(checkpoint.get("entity", "")),
                int(checkpoint.get("instance", 0)), str(checkpoint.get("geometry_stage", "")),
            )
            targets.append({
                **checkpoint,
                "id": str(checkpoint.get("id", "")),
                "layout": str(event.get("layout", "")),
                "time": geometry_times.get(geometry_key, float(checkpoint.get("time", 0.0))),
                "timing_source": "renderer" if geometry_key in geometry_times else "estimated",
                "expected": str(checkpoint.get("expected", "语义动作过程")),
            })
        action_notes = []
        for action in event.get("actions", []):
            if action.get("type") == "collect_parts":
                action_notes.append(f"原有{action.get('count') or ''}份保持尺寸汇集成一组，整组总和为{action.get('total') or '题目已知总数'}")
            elif action.get("type") == "focus_part":
                action_notes.append("红框从整组移动到其中一份，其余等份降低亮度")
            elif action.get("type") == "assemble_whole":
                action_notes.append("等份平滑拼回完整图形，数量与最终答案一致")
        targets.append({
            "id": str(event.get("id", "")),
            "layout": str(event.get("layout", "")),
            "time": measured.get(str(event.get("id", "")), float(event.get("stable", 0.0))),
            "timing_source": "renderer" if str(event.get("id", "")) in measured else "estimated",
            "expected": "；".join(action_notes) or str(event.get("heading", "")) or str(event.get("layout", "")),
        })
    if timeline:
        final_time = max(
            0.1,
            float(timeline[-1].get("video_end", timeline[-1].get("end", 0.0))) - 0.12,
        )
        final_time = measured.get("final_stable", final_time)
        targets.append({"id": "final_stable", "layout": "summary", "time": final_time, "expected": "最终数值已回填原公式，题目与推导无重叠残留"})
    targets.sort(key=lambda item: float(item.get("time", 0.0)))
    deduped: list[dict[str, Any]] = []
    seen: dict[tuple[Any, ...], int] = {}
    for target in targets:
        key = (round(target["time"] * 100),)
        if target.get("geometry_stage"):
            # Simultaneous diagrams need separate checks even when sampled from
            # the same decoded frame; otherwise one bad instance goes unchecked.
            key += (target.get("entity"), target.get("instance", 0), target["geometry_stage"])
        if key not in seen:
            seen[key] = len(deduped)
            deduped.append(_with_measured_center(target, layouts))
        elif target.get("id") == "final_stable":
            # A coincident beat frame must not erase the explicit final check.
            deduped[seen[key]] = _with_measured_center(target, layouts)
    if len(deduped) <= 40:
        return deduped
    # Cover the whole video even when an early section has many checkpoints.
    # Choose known stable frames near evenly spaced times, retaining boundaries.
    selected = {0, len(deduped) - 1}
    selected.update(index for index, target in enumerate(deduped)
                    if target.get("id") in {"title", "final_stable"})
    times = [float(target["time"]) for target in deduped]
    remaining = 40 - len(selected)
    for slot in range(1, remaining + 1):
        desired_time = times[0] + (times[-1] - times[0]) * slot / (remaining + 1)
        next_index = min(
            (index for index in range(len(deduped)) if index not in selected),
            key=lambda index: (abs(times[index] - desired_time), index),
        )
        selected.add(next_index)
    return [deduped[index] for index in sorted(selected)]


def _safe_frame_report(image: Any, target: dict[str, Any], width: int, height: int) -> list[dict[str, Any]]:
    gray = image.convert("L")
    mask = gray.point(lambda value: 255 if value > 28 else 0)
    bbox = mask.getbbox()
    issues: list[dict[str, Any]] = []
    if bbox is None:
        issues.append({"frame": target["id"], "category": "blank", "problem": "稳定关键帧为空白"})
        return issues
    left, top, right, bottom = bbox
    margin_x = max(5, round(width * 0.008))
    margin_y = max(5, round(height * 0.012))
    if left <= margin_x or top <= margin_y or right >= width - margin_x or bottom >= height - margin_y:
        issues.append({
            "frame": target["id"],
            "category": "clipping",
            "problem": f"非黑色内容过于靠近画面边缘：bbox={bbox}，画面={width}×{height}",
        })
    return issues


def _subtitle_free_report(image: Any, target: dict[str, Any], width: int, height: int) -> list[dict[str, Any]]:
    """The bottom narration strip stays empty; mathematical working is above it."""
    area = image.convert("L").crop((0, round(height * 0.91), width, round(height * 0.99)))
    histogram = area.histogram()
    content_pixels = sum(histogram[29:])
    if content_pixels <= max(6, round(width * 0.015)):
        return []
    return [{
        "frame": target.get("id", ""),
        "category": "bottom_subtitle",
        "problem": "底部旁白字幕保留空白区仍有可见内容；请移除逐字稿字幕，正常公式与份数应留在上方推导区",
    }]


def _reference_geometry_report(image: Any, target: dict[str, Any], width: int, height: int) -> list[dict[str, Any]]:
    """Measure the locked reference geometry in actual rendered pixels.

    This catches regressions that syntax checks cannot see: an oversized shape,
    a shifted centre, a pre-partitioned “whole” frame, or an extracted part
    which never actually moved away from the source silhouette.
    """
    stage = str(target.get("geometry_stage", ""))
    kind = str(target.get("kind", ""))
    color = str(target.get("color", ""))
    if stage not in {"whole", "partitioned", "extracted", "diagram_focus"} or kind not in {"circle", "square", "triangle"}:
        return []
    if not color.startswith("#") or len(color) != 7:
        return []
    try:
        expected_rgb = tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))
    except ValueError:
        return []

    slot_count = max(1, int(target.get("slot_count", 1)))
    slot_index = max(0, min(slot_count - 1, int(target.get("slot_index", 0))))
    x_units = 0.0 if slot_count == 1 else -2.88 + 5.76 * slot_index / (slot_count - 1)
    y_units = 0.05
    center = target.get("center")
    if isinstance(center, (list, tuple)) and len(center) >= 2:
        try:
            actual_x, actual_y = float(center[0]), float(center[1])
            if math.isfinite(actual_x) and math.isfinite(actual_y):
                x_units, y_units = actual_x, actual_y
        except (TypeError, ValueError):
            pass
    center_x = (x_units + 4.5) / 9.0 * width
    center_y = (6.0 - y_units) / 12.0 * height
    expected_size = 1.06 / 12.0 * height
    roi_radius_x = expected_size * 0.92
    roi_top = center_y - expected_size * 0.72
    roi_bottom = center_y + expected_size * (1.40 if stage in {"extracted", "diagram_focus"} else 0.72)
    left = max(0, int(center_x - roi_radius_x))
    right = min(width, int(center_x + roi_radius_x) + 1)
    top = max(0, int(roi_top))
    bottom = min(height, int(roi_bottom) + 1)
    pixels = image.load()
    coordinates: list[tuple[int, int]] = []
    for y in range(top, bottom):
        for x in range(left, right):
            actual = pixels[x, y]
            distance = sum((int(actual[channel]) - expected_rgb[channel]) ** 2 for channel in range(3)) ** 0.5
            if distance <= 72:
                coordinates.append((x, y))
    if not coordinates:
        return [{
            "frame": target.get("id", ""),
            "category": "geometry_missing",
            "problem": f"{kind}在参考位置未检测到其锁定颜色，无法验收尺寸与分割动作",
        }]

    xs = [point[0] for point in coordinates]
    ys = [point[1] for point in coordinates]
    bbox_width = max(xs) - min(xs) + 1
    bbox_height = max(ys) - min(ys) + 1
    issues: list[dict[str, Any]] = []
    whole_min = expected_size * 0.78
    whole_max = expected_size * 1.22
    if stage in {"whole", "partitioned"} and not (whole_min <= bbox_height <= whole_max):
        issues.append({
            "frame": target.get("id", ""),
            "category": "geometry_size",
            "problem": f"{kind}视觉高度为{bbox_height}px，应接近统一标准{expected_size:.1f}px",
        })
    if stage == "extracted" and bbox_height < expected_size * 1.25:
        issues.append({
            "frame": target.get("id", ""),
            "category": "extraction_missing",
            "problem": f"{kind}取出一份后的总高度仅{bbox_height}px，未证明选中等份已向下抽离",
        })

    if stage == "diagram_focus":
        box_rgb = (0xF2, 0x3B, 0x42)
        box_pixels = 0
        expanded_left = max(0, int(center_x - expected_size * 0.95))
        expanded_right = min(width, int(center_x + expected_size * 0.95) + 1)
        expanded_top = max(0, int(center_y - expected_size * 0.92))
        expanded_bottom = min(height, int(center_y + expected_size * 1.48) + 1)
        for y in range(expanded_top, expanded_bottom):
            for x in range(expanded_left, expanded_right):
                actual = pixels[x, y]
                distance = sum((int(actual[channel]) - box_rgb[channel]) ** 2 for channel in range(3)) ** 0.5
                if distance <= 88:
                    box_pixels += 1
        if box_pixels < max(10, int(expected_size * 0.30)):
            issues.append({
                "frame": target.get("id", ""),
                "category": "diagram_focus_missing",
                "problem": f"旁白指向{kind}时，参考位置没有检测到红色虚线框",
            })

    expected_width = expected_size * (2 / (3 ** 0.5) if kind == "triangle" else 1.0)
    if stage in {"whole", "partitioned"} and not (expected_width * 0.76 <= bbox_width <= expected_width * 1.24):
        issues.append({
            "frame": target.get("id", ""),
            "category": "geometry_width",
            "problem": f"{kind}视觉宽度为{bbox_width}px，应接近锁定标准{expected_width:.1f}px",
        })

    if stage == "whole" and kind in {"circle", "triangle"}:
        centre_pixels = 0
        for y in range(max(top, int(center_y) - 2), min(bottom, int(center_y) + 3)):
            for x in range(max(left, int(center_x) - 2), min(right, int(center_x) + 3)):
                actual = pixels[x, y]
                distance = sum((int(actual[channel]) - expected_rgb[channel]) ** 2 for channel in range(3)) ** 0.5
                if distance <= 72:
                    centre_pixels += 1
        if centre_pixels >= 4:
            issues.append({
                "frame": target.get("id", ""),
                "category": "premature_partition",
                "problem": f"{kind}完整出现阶段的中心已有分割线，违反先完整图形后分割的顺序",
            })
    return issues


def render_storyboard_preview(
    code: str,
    timeline: list[dict[str, Any]],
    app_dir: Path,
    manim_project: Path,
    python_exe: Path,
) -> dict[str, Any]:
    """Render a persistent preview and sample storyboard-aware stable frames."""
    try:
        import av  # type: ignore
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Manim 环境缺少 PyAV 或 Pillow，无法生成可靠预览") from exc

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    artifact_root = app_dir / "artifacts" / run_id
    artifact_root.mkdir(parents=True, exist_ok=False)
    source_path = artifact_root / "generated_math_video.py"
    media_dir = artifact_root / "media"
    frame_dir = artifact_root / "keyframes"
    frame_dir.mkdir(parents=True, exist_ok=True)
    source_path.write_text(code, encoding="utf-8")

    command = [
        str(_console_python(python_exe)), "-I", "-m", "manim", "-ql", "-r", "360,480", "--fps", "15",
        "--disable_caching", "--config_file", str(retain_config(artifact_root)), "--media_dir", str(media_dir),
        str(source_path), "GeneratedMathVideo",
    ]
    log_path = artifact_root / "render.log"
    completed = _run_render(command, manim_project, 720, log_path, "v3 完整低清预览渲染失败：")
    partial_index(media_dir)
    videos = [
        path for path in media_dir.rglob("*.mp4")
        if "partial_movie_files" not in {part.lower() for part in path.parts}
    ]
    if not videos:
        raise RuntimeError("v3 渲染完成但没有找到完整 MP4；完整日志：" + _redact_render_detail(str(log_path)))
    rendered = max(videos, key=lambda path: path.stat().st_size)
    preview_path = artifact_root / "preview.mp4"
    shutil.copy2(rendered, preview_path)

    container = av.open(str(preview_path))
    stream = container.streams.video[0]
    audio_streams = list(container.streams.audio)
    has_audio = bool(audio_streams)
    rate = float(stream.average_rate or 15)
    duration = float(container.duration / av.time_base) if container.duration else 0.0
    width = int(stream.width)
    height = int(stream.height)
    measured = _measured_stable_times(completed.stdout)
    layout_records = _measured_layouts(completed.stdout)
    geometry_times = _measured_geometry_times(completed.stdout)
    targets = _select_targets(timeline, measured, geometry_times, layout_records)
    keyframes: list[dict[str, Any]] = []
    images: list[str] = []
    motion_records, issues = _motion_report(completed.stdout, timeline)
    formula_action_records, formula_issues = _formula_action_report(completed.stdout, timeline)
    issues.extend(formula_issues)
    contact_images: list[tuple[dict[str, Any], Any]] = []
    def capture_frame(index: int, target: dict[str, Any], frame: Any, seek_time: float) -> None:
        image = frame.to_image().convert("RGB").copy()
        issues.extend(_safe_frame_report(image, target, width, height))
        issues.extend(_subtitle_free_report(image, target, width, height))
        issues.extend(_reference_geometry_report(image, target, width, height))
        filename = f"{index:02d}_{target['id']}_{seek_time:06.2f}s.jpg"
        frame_path = frame_dir / filename
        image.save(frame_path, format="JPEG", quality=90, optimize=True)
        small = image.copy()
        small.thumbnail((540, 720), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        small.save(buffer, format="JPEG", quality=84, optimize=True)
        images.append("data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii"))
        contact = image.copy()
        contact.thumbnail((270, 360), Image.Resampling.LANCZOS)
        contact_images.append((target, contact))
        keyframes.append({
            **target,
            "time": round(seek_time, 2),
            "filename": filename,
            "url": f"/artifacts/{run_id}/keyframes/{filename}",
        })

    # Decode once in chronological order. Repeated random seeks can land on a
    # predictive frame without all reference pixels reconstructed, producing
    # false screenshots where persistent objects appear to vanish.
    target_index = 0
    last_frame = None
    for candidate in container.decode(stream):
        last_frame = candidate
        candidate_time = float(candidate.pts * candidate.time_base) if candidate.pts is not None else 0.0
        while target_index < len(targets):
            target = targets[target_index]
            seek_time = max(0.0, min(float(target["time"]), max(0.0, duration - 0.02)))
            if candidate_time + 1e-3 < seek_time:
                break
            capture_frame(target_index + 1, target, candidate, seek_time)
            target_index += 1
    while target_index < len(targets) and last_frame is not None:
        target = targets[target_index]
        seek_time = max(0.0, min(float(target["time"]), max(0.0, duration - 0.02)))
        capture_frame(target_index + 1, target, last_frame, seek_time)
        target_index += 1
    if target_index != len(targets):
        raise RuntimeError("无法从完整视频顺序解码全部关键帧")
    container.close()

    columns = 3
    rows = (len(contact_images) + columns - 1) // columns
    cell_width = 300
    image_height = 360
    label_height = 46
    sheet = Image.new("RGB", (columns * cell_width, rows * (image_height + label_height)), (12, 14, 18))
    draw = ImageDraw.Draw(sheet)
    font_candidates = [
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "msyh.ttc",
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "msyhbd.ttc",
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "simsun.ttc",
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arial.ttf",
    ]
    label_font = ImageFont.load_default()
    for font_path in font_candidates:
        if not font_path.is_file():
            continue
        try:
            label_font = ImageFont.truetype(str(font_path), 16)
            break
        except OSError:
            continue
    for index, (target, image) in enumerate(contact_images):
        x = (index % columns) * cell_width
        y = (index // columns) * (image_height + label_height)
        image_x = x + (cell_width - image.width) // 2
        image_y = y + label_height + (image_height - image.height) // 2
        sheet.paste(image, (image_x, image_y))
        draw.text(
            (8 + x, 6 + y),
            f"{target['id']}  {target['time']:.2f}s  {target['expected']}",
            fill=(245, 184, 46),
            font=label_font,
        )
    contact_path = artifact_root / "contact_sheet.jpg"
    sheet.save(contact_path, format="JPEG", quality=90, optimize=True)

    report = {
        "run_id": run_id,
        "passed": not issues,
        "duration": round(duration, 2),
        "fps": round(rate, 2),
        "resolution": [width, height],
        "has_audio": has_audio,
        "preview_path": str(preview_path),
        "preview_url": f"/artifacts/{run_id}/preview.mp4",
        "contact_sheet_path": str(contact_path),
        "contact_sheet_url": f"/artifacts/{run_id}/contact_sheet.jpg",
        "keyframes": keyframes,
        "images": images,
        "timestamps": [item["time"] for item in keyframes],
        "frame_count": len(keyframes),
        "measured_stable_frames": len(measured),
        "measured_geometry_frames": len(geometry_times),
        "layout_records": layout_records,
        "motion_records": motion_records,
        "formula_action_records": formula_action_records,
        "issues": issues,
        "summary": "本机完整低清渲染及分镜稳定帧检查通过" if not issues else "稳定帧边界检查发现问题",
    }
    (artifact_root / "report.json").write_text(json.dumps(report | {"images": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def render_storyboard_final(
    code: str,
    timeline: list[dict[str, Any]],
    preview_report: dict[str, Any],
    manim_project: Path,
    python_exe: Path,
) -> dict[str, Any]:
    """Render and verify the actual 1080x1440/60fps deliverable.

    The low-resolution preview and this final render use the exact same frozen
    source file.  Metadata and storyboard-aware stable frames are checked again
    so the UI never reports a merely predicted output path as a finished video.
    """
    try:
        import av  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Manim 环境缺少 PyAV，无法验收高清成片") from exc

    preview_path = Path(str(preview_report.get("preview_path", ""))).resolve()
    if not preview_path.is_file():
        raise RuntimeError("低清预览文件不存在，不能继续生成高清成片")
    artifact_root = preview_path.parent
    source_path = artifact_root / "generated_math_video.py"
    source_path.write_text(code, encoding="utf-8")
    media_dir = artifact_root / "final_media"
    command = [
        str(_console_python(python_exe)), "-I", "-m", "manim", "-qh", "-r", "1080,1440", "--fps", "60",
        "--disable_caching", "--config_file", str(retain_config(artifact_root)), "--media_dir", str(media_dir),
        str(source_path), "GeneratedMathVideo",
    ]
    log_path = artifact_root / "final_render.log"
    completed = _run_render(command, manim_project, 1800, log_path, "1080×1440 60帧成片渲染失败：")
    partial_index(media_dir)
    videos = [
        path for path in media_dir.rglob("*.mp4")
        if "partial_movie_files" not in {part.lower() for part in path.parts}
    ]
    if not videos:
        raise RuntimeError("高清渲染完成但没有找到完整 MP4；完整日志：" + _redact_render_detail(str(log_path)))
    rendered = max(videos, key=lambda path: path.stat().st_size)
    final_path = artifact_root / "final_1080x1440_60fps.mp4"
    shutil.copy2(rendered, final_path)

    container = av.open(str(final_path))
    stream = container.streams.video[0]
    width = int(stream.width)
    height = int(stream.height)
    fps = float(stream.average_rate or 0.0)
    duration = float(container.duration / av.time_base) if container.duration else 0.0
    has_audio = bool(list(container.streams.audio))
    expected_duration = float(preview_report.get("duration", 0.0))
    motion_records, issues = _motion_report(completed.stdout, timeline)
    formula_action_records, formula_issues = _formula_action_report(completed.stdout, timeline)
    issues.extend(formula_issues)
    if (width, height) != (1080, 1440):
        issues.append({"category": "resolution", "problem": f"高清成片分辨率为 {width}×{height}，应为1080×1440"})
    if abs(fps - 60.0) > 0.05:
        issues.append({"category": "fps", "problem": f"高清成片帧率为 {fps:.3f}，应为60fps"})
    if expected_duration and abs(duration - expected_duration) > 0.15:
        issues.append({
            "category": "duration",
            "problem": f"高清成片与已验收预览时长相差 {duration - expected_duration:+.3f} 秒",
        })
    if bool(preview_report.get("has_audio")) and not has_audio:
        issues.append({"category": "audio", "problem": "低清预览含配音，但高清成片没有音轨"})

    layout_records = _measured_layouts(completed.stdout)
    geometry_times = _measured_geometry_times(completed.stdout)
    targets = _select_targets(timeline, _measured_stable_times(completed.stdout), geometry_times, layout_records)
    target_index = 0
    checked_frames = 0
    last_frame = None
    for candidate in container.decode(stream):
        last_frame = candidate
        candidate_time = float(candidate.pts * candidate.time_base) if candidate.pts is not None else 0.0
        while target_index < len(targets):
            target = targets[target_index]
            seek_time = max(0.0, min(float(target["time"]), max(0.0, duration - 0.02)))
            if candidate_time + 1e-3 < seek_time:
                break
            image = candidate.to_image().convert("RGB")
            issues.extend(_safe_frame_report(image, target, width, height))
            issues.extend(_subtitle_free_report(image, target, width, height))
            issues.extend(_reference_geometry_report(image, target, width, height))
            checked_frames += 1
            target_index += 1
    while target_index < len(targets) and last_frame is not None:
        target = targets[target_index]
        image = last_frame.to_image().convert("RGB")
        issues.extend(_safe_frame_report(image, target, width, height))
        issues.extend(_subtitle_free_report(image, target, width, height))
        issues.extend(_reference_geometry_report(image, target, width, height))
        checked_frames += 1
        target_index += 1
    container.close()
    if target_index != len(targets):
        issues.append({"category": "decode", "problem": "高清成片未能解码全部验收时刻"})

    report = {
        "passed": not issues,
        "final_path": str(final_path),
        "final_url": f"/artifacts/{artifact_root.name}/{final_path.name}",
        "duration": round(duration, 3),
        "fps": round(fps, 3),
        "resolution": [width, height],
        "has_audio": has_audio,
        "checked_frames": checked_frames,
        "measured_geometry_frames": len(geometry_times),
        "layout_records": layout_records,
        "motion_records": motion_records,
        "formula_action_records": formula_action_records,
        "issues": issues,
        "size_bytes": final_path.stat().st_size,
        "sha256": hashlib.sha256(final_path.read_bytes()).hexdigest().upper(),
        "summary": "1080×1440 60帧成片及稳定关键帧复验通过" if not issues else "高清成片复验发现问题",
    }
    (artifact_root / "final_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if issues:
        raise RuntimeError("高清成片复验未通过：" + "；".join(str(item.get("problem", item)) for item in issues[:12]))
    return report
