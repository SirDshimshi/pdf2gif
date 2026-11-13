#!/usr/bin/env python3
"""Quick end-to-end test for jpg2gif.

1. Generates sample JPGs whose EXIF timestamps disagree with filename order.
2. Runs --dry-run and checks the resolved order is chronological by EXIF.
3. Builds the GIF and verifies frame count, size, delay, loop, and that the
   frame colors appear in the expected chronological order.
"""

import os
import re
import subprocess
import sys
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(ROOT, "jpg2gif.py")
SAMPLES = os.path.join(HERE, "sample_images")

# Expected chronological order by EXIF DateTimeOriginal -> colors.
EXPECTED_COLORS = [
    (0, 255, 0),      # img_2.jpg  2024:01:02
    (255, 0, 255),    # img_3.jpg  2024:01:20
    (0, 0, 255),      # img_1.jpg  2024:02:14
    (255, 255, 0),    # img_20.jpg 2024:03:01
    (255, 0, 0),      # img_10.jpg 2024:03:05
]
EXPECTED_NAMES = ["img_2.jpg", "img_3.jpg", "img_1.jpg", "img_20.jpg", "img_10.jpg"]


def run(args):
    return subprocess.run([sys.executable, TOOL] + args, capture_output=True, text=True)


def main():
    subprocess.run([sys.executable, os.path.join(HERE, "make_sample_images.py"), SAMPLES],
                   check=True, capture_output=True)

    dry = run(["--input", SAMPLES, "--dry-run"])
    assert dry.returncode == 0, dry.stderr
    order = [re.match(r"\s*\d+\.\s+(\S+)", l).group(1)
             for l in dry.stdout.splitlines() if re.match(r"\s*\d+\.\s+\S+", l)]
    assert order == EXPECTED_NAMES, f"dry-run order mismatch: {order}"
    print("PASS: --dry-run lists frames in chronological EXIF order")

    with tempfile.TemporaryDirectory() as tmp:
        out_gif = os.path.join(tmp, "sample.gif")
        res = run(["--input", SAMPLES, "--output", out_gif,
                   "--delay", "200", "--max-width", "400"])
        assert res.returncode == 0, res.stderr
        with Image.open(out_gif) as gif:
            assert getattr(gif, "is_animated", False), "GIF is not animated"
            assert gif.n_frames == len(EXPECTED_COLORS), f"frame count {gif.n_frames}"
            assert gif.info.get("duration") == 200, gif.info.get("duration")
            assert gif.info.get("loop") == 0, "expected infinite loop"
            assert gif.size == (400, 300), gif.size
            for i, expected in enumerate(EXPECTED_COLORS):
                gif.seek(i)
                px = gif.convert("RGB").getpixel((gif.size[0] // 2, gif.size[1] // 2))
                assert all(abs(a - b) <= 2 for a, b in zip(px, expected)), \
                    f"frame {i}: color {px} != {expected}"
    print("PASS: GIF has 5 frames, 400x300, 200 ms, infinite loop, correct chronological colors")

    with tempfile.TemporaryDirectory() as tmp:
        empty = os.path.join(tmp, "empty")
        os.makedirs(empty)
        res = run(["--input", empty])
        assert res.returncode == 1, "expected exit code 1 for empty folder"
        assert "no JPG/JPEG images" in res.stderr, res.stderr
    print("PASS: empty folder exits with a clear error")

    print("All tests passed.")


if __name__ == "__main__":
    main()
