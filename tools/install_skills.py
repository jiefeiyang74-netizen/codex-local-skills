"""Install bundled skills with explicit selection and reversible replacement."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone
from uuid import uuid4

SKILLS = ("app-factory", "manim-math-workbench", "replace-logo-with-cutout")
REPOSITORY = Path(__file__).resolve().parents[1]


def is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def default_destination() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return (Path(configured).expanduser() if configured else Path.home() / ".codex") / "skills"


def install(names: list[str], destination: Path, *, replace: bool = False,
            dry_run: bool = False) -> list[str]:
    if not names or any(name not in SKILLS for name in names):
        raise ValueError("Select one or more bundled skill names.")
    destination = destination.expanduser().resolve()
    plans = []
    for name in dict.fromkeys(names):
        source = REPOSITORY / "skills" / name
        target = destination / name
        source_resolved = source.resolve()
        target_resolved = target.resolve()
        if is_link(REPOSITORY / "skills") or not source_resolved.is_relative_to(REPOSITORY.resolve()):
            raise ValueError(f"Skill source escapes the bundled repository: {name}")
        if target_resolved.is_relative_to(source_resolved) or source_resolved.is_relative_to(target_resolved):
            raise ValueError(f"Source and destination must not overlap: {name}")
        if not (source / "SKILL.md").is_file():
            raise ValueError(f"Missing skill entrypoint: {name}")
        if any(is_link(path) for path in source.rglob("*")) or is_link(source):
            raise ValueError(f"Linked source files are not supported: {name}")
        if is_link(target):
            raise ValueError(f"Refusing to replace a linked destination: {target}")
        if target.exists() and not replace:
            raise FileExistsError(f"Already installed: {target}; use --replace to create a backup first.")
        if target.exists() and not target.is_dir():
            raise ValueError(f"Destination is not a directory: {target}")
        backup_directory = destination / ".backups"
        if replace and target.exists() and (
            is_link(backup_directory) or not backup_directory.resolve().is_relative_to(destination)
        ):
            raise ValueError(f"Refusing a linked backup directory: {backup_directory}")
        plans.append((name, source, target))
    if dry_run:
        return [f"Would install {name} -> {target}" for name, _, target in plans]
    destination.mkdir(parents=True, exist_ok=True)
    completed = []
    for name, source, target in plans:
        staging = destination / f".{name}.install-{uuid4().hex}"
        backup = None
        try:
            shutil.copytree(source, staging, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
            if target.exists():
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                backup = destination / ".backups" / f"{name}-{stamp}-{uuid4().hex[:8]}"
                backup.parent.mkdir(parents=True, exist_ok=True)
                target.rename(backup)
            staging.rename(target)
            message = f"Installed {name} -> {target}"
            if backup:
                message += f"; previous version -> {backup}"
            completed.append(message)
        except Exception as error:
            if backup is not None and backup.exists() and not target.exists():
                backup.rename(target)
            if completed:
                raise RuntimeError(
                    f"Installation stopped at {name}: {error}\n"
                    "Already completed (retained):\n" + "\n".join(completed)
                ) from error
            raise
        finally:
            if staging.exists():
                # staging is generated inside the resolved destination above.
                if staging.parent.resolve() != destination:
                    raise RuntimeError("Unexpected staging location.")
                shutil.rmtree(staging)
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--list", action="store_true", help="List bundled skills.")
    selection.add_argument("--all", action="store_true", help="Install all three skills.")
    selection.add_argument("--skill", action="append", choices=SKILLS, help="Repeat to select multiple skills.")
    parser.add_argument("--target", type=Path, default=default_destination(), help="Actual skill discovery directory.")
    parser.add_argument("--replace", action="store_true", help="Back up existing directories before replacing them.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned paths without writing files.")
    args = parser.parse_args()
    if args.list:
        print("\n".join(SKILLS))
        return 0
    try:
        for message in install(list(SKILLS) if args.all else args.skill, args.target,
                               replace=args.replace, dry_run=args.dry_run):
            print(message)
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
