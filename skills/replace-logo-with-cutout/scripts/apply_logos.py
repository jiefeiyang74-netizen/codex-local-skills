"""Composite supplied logo pixels onto a base and save a new lossless PNG."""

import argparse
import json
import math
from pathlib import Path
import warnings

from PIL import Image


def integer(value, name: str, minimum: int, maximum=None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        limit = f"{minimum}..{maximum}" if maximum is not None else f">= {minimum}"
        raise ValueError(f"{name} must be {limit}")
    return value


def coordinate(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(f"{name} must be a finite number") from error
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def open_rgba(path: Path) -> Image.Image:
    # Keep Pillow's large-image protection and close source files promptly.
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as source:
            return source.convert("RGBA")


def cutout(path: Path, crop=None, threshold: int = 235,
           remove_white: bool = True) -> Image.Image:
    threshold = integer(threshold, "white_threshold", 1, 255)
    if not isinstance(remove_white, bool):
        raise ValueError("remove_white must be true or false")
    image = open_rgba(path)
    if crop is not None:
        if not isinstance(crop, list) or len(crop) != 4:
            raise ValueError("crop must be [left, top, right, bottom]")
        left, top, right, bottom = [integer(v, "crop coordinate", 0) for v in crop]
        if not (left < right <= image.width and top < bottom <= image.height):
            raise ValueError("crop must have positive size and stay inside the logo")
        image = image.crop((left, top, right, bottom))
    if remove_white:
        pixels = image.load()
        soft_start = max(0, threshold - 30)
        for y in range(image.height):
            for x in range(image.width):
                red, green, blue, original_alpha = pixels[x, y]
                brightness = min(red, green, blue)
                if brightness >= threshold:
                    pixels[x, y] = (red, green, blue, 0)
                elif brightness >= soft_start:
                    # Multiply existing alpha: never make transparent pixels opaque.
                    alpha = round(original_alpha * (threshold - brightness)
                                  / (threshold - soft_start))
                    pixels[x, y] = (red, green, blue, alpha)
    bounds = image.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError("logo has no visible pixels after crop/background removal")
    return image.crop(bounds)


def logo_path(item: dict, specs_dir: Path) -> Path:
    value = item.get("path")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path must be a non-empty file path")
    path = Path(value)
    return (path if path.is_absolute() else specs_dir / path).resolve()


def composite(base: Image.Image, item: dict, specs_dir: Path) -> None:
    if not isinstance(item, dict):
        raise ValueError("placement must be a JSON object")
    required = ("path", "cx", "cy", "max_width", "max_height")
    missing = [key for key in required if key not in item]
    if missing:
        raise ValueError(f"missing placement fields: {', '.join(missing)}")
    width = integer(item["max_width"], "max_width", 1)
    height = integer(item["max_height"], "max_height", 1)
    cx = coordinate(item["cx"], "cx")
    cy = coordinate(item["cy"], "cy")
    if not (0 <= cx <= base.width and 0 <= cy <= base.height):
        raise ValueError("logo center must stay inside the base image")
    logo = cutout(logo_path(item, specs_dir), item.get("crop"),
                  item.get("white_threshold", 235), item.get("remove_white", True))
    logo.thumbnail((width, height), Image.Resampling.LANCZOS)
    x = round(cx - logo.width / 2)
    y = round(cy - logo.height / 2)
    if x < 0 or y < 0 or x + logo.width > base.width or y + logo.height > base.height:
        raise ValueError("placed logo extends beyond the base; adjust size or center")
    base.alpha_composite(logo, (x, y))


def apply_logos(base_path: Path, output_path: Path, specs_path: Path) -> None:
    base_path = base_path.resolve()
    output_path = output_path.resolve()
    specs_path = specs_path.resolve()
    if output_path.suffix.lower() != ".png":
        raise ValueError("output must use .png to preserve pixels and transparency")
    if output_path in (base_path, specs_path):
        raise ValueError("output must differ from the base and placement file")
    if output_path.exists():
        raise ValueError("output already exists; choose a new output filename")
    with specs_path.open(encoding="utf-8-sig") as file:
        items = json.load(file)
    if not isinstance(items, list) or not items:
        raise ValueError("logo-specs must be a non-empty JSON array")
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise ValueError(f"placement {index}: must be a JSON object")
        if output_path == logo_path(item, specs_path.parent):
            raise ValueError(f"placement {index}: output must differ from every logo")
    base = open_rgba(base_path)
    for index, item in enumerate(items, 1):
        try:
            composite(base, item, specs_path.parent)
        except (ValueError, OSError) as error:
            raise ValueError(f"placement {index}: {error}") from error
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation rejects a destination created during processing.
    with output_path.open("xb") as file:
        base.save(file, format="PNG")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--logo-specs", required=True, type=Path)
    args = parser.parse_args()
    try:
        apply_logos(args.base, args.output, args.logo_specs)
    except (ValueError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        parser.error(str(error))
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
