"""Check distributable skills, public-file boundaries and local references."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {"app-factory", "manim-math-workbench", "replace-logo-with-cutout"}
SECRET_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{35,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
PRIVATE_PATH = re.compile(r"(?i)\b[A-Z]:[\\/]+(?:Users|Codex)[\\/]+")
LINK = re.compile(r"\[[^\]\n]*\]\(([^\n]+?)\)")
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".pem", ".key",
                      ".wav", ".mp3", ".mp4", ".mov", ".zip", ".log"}
IGNORED_PARTS = {".git", "__pycache__"}


def collect_files() -> tuple[list[Path], list[str]]:
    entries, errors = [], []
    def linked_or_escaping(path: Path) -> bool:
        linked = path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())
        return linked or not path.resolve().is_relative_to(ROOT)
    for directory, subdirectories, filenames in os.walk(ROOT, topdown=True, followlinks=False):
        parent = Path(directory)
        retained = []
        for name in subdirectories:
            if name in IGNORED_PARTS:
                continue
            path = parent / name
            if linked_or_escaping(path):
                errors.append(f"Linked or escaping repository path: {path.relative_to(ROOT).as_posix()}")
            else:
                retained.append(name)
        subdirectories[:] = retained
        for name in filenames:
            path = parent / name
            if linked_or_escaping(path):
                errors.append(f"Linked or escaping repository path: {path.relative_to(ROOT).as_posix()}")
            elif path.is_file():
                entries.append(path)
    return sorted(entries), errors


def files() -> list[Path]:
    entries, errors = collect_files()
    if errors:
        raise ValueError("\n".join(errors))
    return entries


def validate() -> tuple[list[str], int]:
    entries, errors = collect_files()
    if errors:
        return errors, len(entries)
    actual = {p.name for p in (ROOT / "skills").iterdir() if p.is_dir()}
    if actual != EXPECTED:
        errors.append(f"Skill directories differ: {sorted(actual)}")
    for name in sorted(EXPECTED):
        base = ROOT / "skills" / name
        for required in ("SKILL.md", "README.md", "LICENSE", "agents/openai.yaml"):
            if not (base / required).is_file():
                errors.append(f"Missing {name}/{required}")
        skill_file = base / "SKILL.md"
        if not skill_file.exists():
            continue
        text = skill_file.read_text(encoding="utf-8-sig")
        match = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)", text, re.S)
        if not match:
            errors.append(f"Missing frontmatter: {name}")
            continue
        try:
            metadata = yaml.safe_load(match.group(1))
            if not isinstance(metadata, dict):
                errors.append(f"Frontmatter must be a mapping: {name}")
                continue
            if metadata.get("name") != name:
                errors.append(f"Invalid skill name: {name}")
            if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
                errors.append(f"Missing description: {name}")
            ui = yaml.safe_load((base / "agents/openai.yaml").read_text(encoding="utf-8-sig"))
            if not isinstance(ui, dict) or not isinstance(ui.get("interface"), dict):
                errors.append(f"Invalid UI metadata: {name}")
        except (ValueError, OSError, yaml.YAMLError) as error:
            errors.append(f"Invalid metadata: {name}: {error}")
    for path in entries:
        relative = path.relative_to(ROOT).as_posix()
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            errors.append(f"Linked file: {relative}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name.startswith(".env"):
            errors.append(f"Forbidden distributable: {relative}")
        if path.stat().st_size > 20 * 1024 * 1024:
            errors.append(f"Unexpected large file: {relative}")
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            # Only generic visual examples explicitly documented in the skill may be binary.
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".ico"}:
                errors.append(f"Unexpected binary file: {relative}")
            continue
        if PRIVATE_PATH.search(text):
            errors.append(f"Private absolute machine path: {relative}")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            errors.append(f"Possible secret: {relative}")
        if path.suffix.lower() == ".py":
            try:
                ast.parse(text, filename=relative)
            except SyntaxError as error:
                errors.append(f"Python syntax: {relative}:{error.lineno}: {error.msg}")
        if path.suffix.lower() == ".json":
            try:
                json.loads(text)
            except ValueError as error:
                errors.append(f"JSON syntax: {relative}: {error}")
        if path.suffix.lower() in {".yaml", ".yml"}:
            try:
                yaml.safe_load(text)
            except yaml.YAMLError as error:
                errors.append(f"YAML syntax: {relative}: {error}")
        if path.suffix.lower() == ".md":
            for raw in LINK.findall(text):
                raw = raw.strip().split(' "', 1)[0].strip("<>")
                parsed = urlsplit(raw)
                if parsed.scheme or raw.startswith("#") or any(c in raw for c in "{}$"):
                    continue
                local = unquote(parsed.path)
                if not local:
                    continue
                target = (path.parent / local).resolve()
                if not target.is_relative_to(ROOT) or not target.exists():
                    errors.append(f"Broken local link: {relative} -> {local}")
    manifest_file = ROOT / "RELEASE-FILES.json"
    if manifest_file.exists():
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest_entries = manifest.get("files", [])
        expected_paths = {entry["path"] for entry in manifest_entries}
        actual_paths = {p.relative_to(ROOT).as_posix() for p in entries if p != manifest_file}
        if len(expected_paths) != len(manifest_entries) or expected_paths != actual_paths:
            errors.append("Manifest contains duplicates or differs from distributable file paths.")
        for entry in manifest_entries:
            target = (ROOT / entry["path"]).resolve()
            if not target.is_relative_to(ROOT) or not target.is_file():
                errors.append(f"Invalid manifest path: {entry['path']}")
                continue
            if hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]:
                errors.append(f"Manifest hash mismatch: {entry['path']}")
    return errors, len(entries)


if __name__ == "__main__":
    failures, count = validate()
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        raise SystemExit(1)
    print(f"Validated {len(EXPECTED)} skills and {count} distributable files.")
