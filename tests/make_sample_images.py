#!/usr/bin/env python3
"""Generate a small sample set of JPGs with scrambled EXIF timestamps.

Filenames are deliberately not in chronological order (img_2 vs img_10) so
the chronological EXIF ordering of jpg2gif is actually exercised.
Each frame is a distinct solid color so the GIF frame order can be verified
by inspecting pixel colors.
"""

import os
import sys

from PIL import Image

# (filename, EXIF DateTimeOriginal, RGB color)
SAMPLES = [
    ("img_10.jpg", "2024:03:05 12:00:00", (255, 0, 0)),     # red,   latest
    ("img_2.jpg",  "2024:01:02 08:30:00", (0, 255, 0)),     # green, earliest
    ("img_1.jpg",  "2024:02:14 17:45:00", (0, 0, 255)),     # blue
    ("img_20.jpg", "2024:03:01 09:15:00", (255, 255, 0)),   # yellow
    ("img_3.jpg",  "2024:01:20 11:00:00", (255, 0, 255)),   # magenta
]


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "sample_images")
    os.makedirs(out_dir, exist_ok=True)
    for name, dt, color in SAMPLES:
        img = Image.new("RGB", (1200, 900), color)
        exif = Image.Exif()
        exif[36867] = dt  # DateTimeOriginal
        exif[306] = dt    # DateTime
        path = os.path.join(out_dir, name)
        img.save(path, "JPEG", exif=exif.tobytes())
        print(f"wrote {path} (EXIF {dt}, color {color})")
    print(f"Sample set ready in {out_dir}")


if __name__ == "__main__":
    main()
