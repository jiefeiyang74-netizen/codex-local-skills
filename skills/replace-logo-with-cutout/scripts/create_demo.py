"""Create an unbranded example base, synthetic logo pixels and placements."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


def create_demo(folder: Path) -> None:
    names = ("base.png", "symbol.png", "placements.json")
    if any((folder / name).exists() for name in names):
        raise ValueError("demo inputs already exist; choose a new output directory")
    folder.mkdir(parents=True, exist_ok=True)
    base = Image.new("RGBA", (480, 320), (24, 37, 54, 255))
    draw = ImageDraw.Draw(base)
    draw.rectangle((30, 30, 450, 110), fill=(49, 69, 90, 255))
    draw.rectangle((30, 150, 450, 290), fill=(31, 48, 66, 255))
    symbol = Image.new("RGBA", (100, 80), (255, 255, 255, 255))
    draw = ImageDraw.Draw(symbol)
    draw.polygon(((25, 60), (50, 20), (75, 60)), fill=(247, 166, 48, 255))
    for name, image in (("base.png", base), ("symbol.png", symbol)):
        with (folder / name).open("xb") as file:
            image.save(file, format="PNG")
    items = [{"path": "symbol.png", "cx": 240, "cy": 220,
              "max_width": 70, "max_height": 60}]
    with (folder / "placements.json").open("x", encoding="utf-8") as file:
        json.dump(items, file, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        create_demo(args.output_dir)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f"Created synthetic demo inputs in: {args.output_dir}")


if __name__ == "__main__":
    main()
