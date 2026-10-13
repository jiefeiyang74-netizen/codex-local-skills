---
name: replace-logo-with-cutout
description: Replace incorrect logos in posters and social images with supplied original pixel assets, optionally removing near-white backgrounds. Use when the surrounding image must remain unchanged and exact logos must not be redrawn by AI.
license: MIT
---

# Replace logos with original cutouts

Use original logo assets as pixels. Never ask an image model to redraw a logo.

## Workflow

1. Inspect the base image and logo masters. Record logo order, target size, coordinates, and output dimensions.
2. If an old logo would show through, use image editing only to erase its footprint and restore its nearby background. Lock all other content: text, characters, decoration, layout, and canvas size.
3. Run `scripts/apply_logos.py` to remove white/near-white artboards and alpha-composite supplied original logos onto the clean base. For transparent masters with intended white artwork, set `remove_white: false`: threshold removal also affects internal near-white pixels.
4. Inspect at 100%: verify no white card/background, no old-logo ghosting, correct order, readable details, and unchanged surrounding content.
5. Save a new PNG output file; never overwrite the user's base image or other inputs. The script rejects existing destinations and keeps the base dimensions and alpha outside the placed logos.

## Script

```powershell
python "<skill-directory>/scripts/apply_logos.py" --base clean-base.png --output final.png --logo-specs placements.json
```

Requires Python 3.10+ and Pillow; install with `python -m pip install -r "<skill-directory>/requirements.txt"`. No image-generation API is required for the pixel-compositing step.

Each placement needs `path`, `cx`, `cy`, `max_width`, and `max_height`. Optional fields: `crop` (`[left, top, right, bottom]`), `white_threshold` (integer `1..255`, default `235`), and `remove_white` (boolean, default `true`). Relative logo paths resolve from the JSON file's directory. Coordinates are pixels in the base image; the trimmed logo is centered at `cx, cy`, keeps its aspect ratio, and is only shrunk to fit the maximum integer dimensions. Out-of-canvas placements are rejected rather than silently clipped.

```json
[
  {"path":"logo-1.png","cx":75,"cy":151,"max_width":125,"max_height":142},
  {"path":"logo-2.png","cx":238,"cy":153,"max_width":150,"max_height":135,"crop":[25,20,545,495]}
]
```

Read [README.md](README.md) for standalone installation and a runnable example using synthetic shapes, without any real brand assets.

## Clean-base prompt

```text
Only erase the existing logo areas and restore their immediate background.
Do not change any other text, person, colour, decoration, layout, or pixel outside those logo areas.
Do not draw replacement logos.
```
