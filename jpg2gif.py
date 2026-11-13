#!/usr/bin/env python3
"""jpg2gif - convert a set of JPG images (or a PDF) into a single animated GIF.

Frames are ordered chronologically: EXIF DateTimeOriginal, then EXIF
DateTime, then file modification time, then natural filename sort.
"""

import argparse
import os
import re
import sys
import tempfile
from datetime import datetime

try:
    from PIL import Image
except ImportError:
    sys.stderr.write("Error: Pillow is required. Install it with: pip install pillow\n")
    sys.exit(1)

IMAGE_EXTENSIONS = {".jpg", ".jpeg"}
EXIF_DATETIME_ORIGINAL = 36867
EXIF_DATETIME = 306
EXIF_TIME_FORMAT = "%Y:%m:%d %H:%M:%S"


def natural_key(name):
    """Natural sort key: img_2 sorts before img_10."""
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", os.path.basename(name))]


def read_exif_timestamp(path):
    """Return (timestamp, source) using EXIF DateTimeOriginal, then EXIF DateTime."""
    try:
        with Image.open(path) as img:
            exif = img.getexif()
    except Exception:
        return None, None
    for tag, source in ((EXIF_DATETIME_ORIGINAL, "EXIF DateTimeOriginal"),
                        (EXIF_DATETIME, "EXIF DateTime")):
        value = exif.get(tag)
        if value:
            try:
                dt = datetime.strptime(str(value).strip(), EXIF_TIME_FORMAT)
                return dt.timestamp(), source
            except ValueError:
                continue
    return None, None


def collect_image_files(paths):
    """Expand input paths (folders, files, PDFs) into a list of image file paths."""
    files = []
    pdfs = []
    for path in paths:
        if not os.path.exists(path):
            sys.stderr.write(f"Error: input path does not exist: {path}\n")
            sys.exit(1)
        if os.path.isdir(path):
            found = sorted(
                os.path.join(path, name) for name in os.listdir(path)
                if os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS
                and os.path.isfile(os.path.join(path, name))
            )
            files.extend(found)
        elif os.path.splitext(path)[1].lower() == ".pdf" or is_pdf_file(path):
            pdfs.append(path)
        elif os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS:
            files.append(path)
        else:
            sys.stderr.write(f"Error: unsupported input file type: {path}\n")
            sys.exit(1)
    return files, pdfs


def is_pdf_file(path):
    try:
        with open(path, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def extract_pdf_images(pdf_path):
    """Extract embedded images (one per page, in page order) to a temp dir."""
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.stderr.write("Error: PDF input requires pypdf. Install it with: pip install pypdf\n")
        sys.exit(1)

    tmpdir = tempfile.mkdtemp(prefix="jpg2gif_pdf_")
    extracted = []
    reader = PdfReader(pdf_path)
    for page_index, page in enumerate(reader.pages, start=1):
        try:
            images = list(page.images)
        except Exception:
            images = []
        if not images:
            sys.stderr.write(f"Warning: page {page_index} of {pdf_path} has no embedded image; skipped.\n")
            continue
        for img_index, image in enumerate(images):
            name = image.name or "image.png"
            ext = os.path.splitext(name)[1].lower().lstrip(".") or "png"
            if ext not in {"png", "jpg", "jpeg", "jp2", "bmp", "tiff"}:
                ext = "png"
            out_path = os.path.join(tmpdir, f"page_{page_index:03d}_{img_index}.{ext}")
            with open(out_path, "wb") as fh:
                fh.write(image.data)
            extracted.append(out_path)
    return extracted


def resolve_frame_order(files, from_pdf=False):
    """Sort frames chronologically and return a list of (path, sort_key, source)."""
    if from_pdf:
        ordered = sorted(files, key=natural_key)
        return [(path, natural_key(path), "PDF page order") for path in ordered]

    keyed = []
    missing_exif = 0
    for path in files:
        ts, source = read_exif_timestamp(path)
        if ts is None:
            missing_exif += 1
            source = "file mtime"
            ts = os.path.getmtime(path)
        keyed.append((path, (ts, natural_key(path)), source))

    if missing_exif:
        sys.stderr.write(
            f"Warning: EXIF timestamp missing on {missing_exif} of {len(files)} file(s); "
            "fell back to modification time for those.\n"
        )

    keyed.sort(key=lambda item: item[1])
    return keyed


def print_frame_order(frames):
    print(f"Resolved frame order ({len(frames)} frame(s)):")
    for i, (path, _key, source) in enumerate(frames, start=1):
        print(f"  {i:>3}. {os.path.basename(path)}  [{source}]")


def load_frame(path, max_width):
    """Load an image, flatten onto white RGB, and scale to fit max_width."""
    with Image.open(path) as img:
        img.load()
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background
        else:
            img = img.convert("RGB")
        width, height = img.size
        largest = max(width, height)
        if largest > max_width:
            scale = max_width / largest
            new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
            img = img.resize(new_size, Image.LANCZOS)
        return img


def build_gif(frames, output_path, delay, max_width, loop):
    paths = [path for path, _key, _source in frames]
    images = [load_frame(path, max_width) for path in paths]
    if not images:
        sys.stderr.write("Error: no frames to write into the GIF.\n")
        sys.exit(1)
    loop_count = 0 if loop else 1
    images[0].save(
        output_path,
        save_all=True,
        append_images=images[1:],
        duration=delay,
        loop=loop_count,
        optimize=False,
    )
    size = images[0].size
    print(f"Wrote {output_path} ({len(images)} frames, {size[0]}x{size[1]} px, "
          f"{delay} ms/frame, {'infinite loop' if loop else 'plays once'})")


def default_output_path(inputs):
    first = inputs[0]
    base = first if os.path.isdir(first) else os.path.splitext(first)[0]
    return os.path.basename(base.rstrip(os.sep)) + ".gif"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="jpg2gif",
        description="Convert JPG images (or a PDF) into a single animated GIF, "
                    "ordered chronologically.",
    )
    parser.add_argument("--input", nargs="+", required=True, metavar="PATH",
                        help="Folder, image file(s), or PDF to convert.")
    parser.add_argument("--output", metavar="PATH.gif", default=None,
                        help="Output GIF path (default: input name + .gif).")
    parser.add_argument("--delay", type=int, default=250, metavar="MS",
                        help="Frame delay in milliseconds (default: 250).")
    parser.add_argument("--max-width", type=int, default=800, metavar="PX",
                        help="Maximum frame dimension in pixels (default: 800).")
    parser.add_argument("--no-loop", action="store_true",
                        help="Play the GIF once instead of looping infinitely.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the resolved frame order and skip GIF creation.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.delay <= 0:
        sys.stderr.write("Error: --delay must be a positive number of milliseconds.\n")
        sys.exit(1)
    if args.max_width <= 0:
        sys.stderr.write("Error: --max-width must be a positive number of pixels.\n")
        sys.exit(1)

    files, pdfs = collect_image_files(args.input)
    from_pdf = False
    if pdfs:
        if len(pdfs) > 1:
            sys.stderr.write("Error: only one PDF input is supported.\n")
            sys.exit(1)
        files = extract_pdf_images(pdfs[0])
        from_pdf = True

    if not files:
        sys.stderr.write("Error: no JPG/JPEG images found in the given input.\n")
        sys.exit(1)

    frames = resolve_frame_order(files, from_pdf=from_pdf)
    print_frame_order(frames)

    if args.dry_run:
        print("Dry run: skipping GIF creation.")
        return 0

    output = args.output or default_output_path(args.input)
    build_gif(frames, output, args.delay, args.max_width, loop=not args.no_loop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
