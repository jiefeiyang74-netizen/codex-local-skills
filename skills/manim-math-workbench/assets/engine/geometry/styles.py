"""Bounded style sidecar; storyboard/request schemas stay unchanged."""
import json
from pathlib import Path
STYLES = ("classic_black", "paper_guided")

def check_style(value):
    if type(value) is not str or value not in STYLES:
        raise ValueError("Unknown selected_style; use classic_black or paper_guided")
    return value

def load_selection(request_path):
    path = Path(request_path).parent / "style-selection.json"
    if not path.exists():
        return {"schema_version": 1, "selected_style": "classic_black"}
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("style-selection.json must be an object")
    if not {"schema_version", "selected_style"} <= set(raw) or set(raw) - {"schema_version", "selected_style", "selection_source"}:
        raise ValueError("style-selection.json requires schema_version/selected_style and optional selection_source")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError("Unsupported style-selection schema_version")
    if "selection_source" in raw and (not isinstance(raw["selection_source"], str) or not 0 < len(raw["selection_source"]) <= 500):
        raise ValueError("Invalid selection_source")
    check_style(raw["selected_style"])
    return raw

def style_contract():
    return {"sidecar": "style-selection.json beside request.json", "schema_version": 1,
            "selected_style": list(STYLES), "legacy_missing_sidecar": "classic_black",
            "paper_guided_pipeline": "geometry-1.0 only; generic/v3 rejects it",
            "reference": "references/visual-styles.md"}
