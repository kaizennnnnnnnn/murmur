"""Render the Murmur app icon to a multi-resolution .ico file on disk so
Windows shortcuts can point at it. Run once after icon changes.

Uses Pillow with LANCZOS resampling for crisp downscaling from the
1254px source. Qt's SmoothTransformation is bilinear and gets soft on
large downscales (≈39× shrink to 32px), which is why we bypass Qt here
and go straight from the original PNG."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
src = ROOT / "assets" / "WhiteIcon.png"
out = ROOT / "Murmur.ico"

img = Image.open(src).convert("RGBA")
w, h = img.size

# Detect the head bounding box and crop tightly around it. A loose
# 78%-of-source crop leaves the head filling only ~72% of the icon —
# at 32px that means each face feature gets ~23px of room, which goes
# muddy. Detecting the head box lets us push the head to ~88% fill
# so the eyes/mouth survive the downscale.
import numpy as np
gray = np.array(img.convert("L"))
# Foreground = anything above near-black. Look only in the upper 55%
# so the white bodysuit below the chin isn't pulled into the bbox.
mask = gray[:int(h * 0.55), :] > 40
rows = np.where(mask.any(axis=1))[0]
cols = np.where(mask.any(axis=0))[0]
hx0, hx1 = int(cols.min()), int(cols.max())
hy0, hy1 = int(rows.min()), int(rows.max())
hcx = (hx0 + hx1) // 2
hcy = (hy0 + hy1) // 2
head_side = max(hx1 - hx0, hy1 - hy0)
# Small breathing-room margin so the hair doesn't kiss the icon edge.
side = int(head_side * 1.15)
x = max(0, hcx - side // 2)
y = max(0, hcy - side // 2)
if x + side > w:
    x = w - side
if y + side > h:
    y = h - side
cropped = img.crop((x, y, x + side, y + side))

# Include every size Windows might ask for so it never has to scale at
# render time — taskbar (32), large icons (48), jumbo (96, 128), shell
# extra-large (256). Skipping 16 and 24 because crisp pixel-art line work
# at that resolution requires hand-tuned hinting, not photo downscaling.
sizes = [16, 24, 32, 48, 64, 96, 128, 256]
images = []
for size in sizes:
    images.append(cropped.resize((size, size), Image.LANCZOS))

images[-1].save(
    out,
    format="ICO",
    sizes=[(im.width, im.height) for im in images],
    append_images=images[:-1],
)
print(f"wrote {out} ({len(images)} sizes: {sizes})")
