# jpg2gif

A small Python CLI tool that converts a set of JPG images — or a PDF — into a
single animated GIF, with frames ordered strictly chronologically.

## Install

```bash
pip install -r requirements.txt   # pillow, plus pypdf for PDF input mode
```

## Usage

```bash
# Folder of JPGs -> animated GIF (default output: <folder name>.gif)
python jpg2gif.py --input ./photos

# Explicit output, custom delay and size
python jpg2gif.py --input ./photos --output animation.gif --delay 500 --max-width 1024

# A list of individual files
python jpg2gif.py --input img_a.jpg img_b.jpg img_c.jpg --output out.gif

# PDF input: embedded images are extracted one per page and used as frames
python jpg2gif.py --input slides.pdf --output slides.gif

# Preview the resolved frame order without creating a GIF
python jpg2gif.py --input ./photos --dry-run

# Play once instead of looping forever
python jpg2gif.py --input ./photos --no-loop
```

### Flags

| Flag | Default | Description |
| --- | --- | --- |
| `--input PATH [PATH ...]` | (required) | Folder, image file(s), or PDF |
| `--output PATH.gif` | input name + `.gif` | Output GIF path |
| `--delay MS` | `250` | Frame delay in milliseconds |
| `--max-width PX` | `800` | Max frame dimension; aspect ratio preserved |
| `--no-loop` | infinite loop | Play the GIF once |
| `--dry-run` | off | Print frame order, skip GIF creation |

### Frame ordering

Frames are sorted chronologically, per file, using the first available of:

1. EXIF `DateTimeOriginal`
2. EXIF `DateTime`
3. File modification time (a warning is printed for files without EXIF)
4. Natural filename sort (`img_2` before `img_10`) as the final tie-breaker

The resolved order is always printed before the GIF is built. For PDF input,
frames follow page order.

### Frame normalization

All frames are converted to RGB on a white background (alpha and CMYK are
handled) and scaled to fit within `--max-width` while preserving aspect ratio.

## Quick test

```bash
python tests/make_sample_images.py tests/sample_images   # generate 5 sample JPGs
python tests/test_jpg2gif.py                            # dry-run order + GIF verification
```

The sample set uses filenames that disagree with their EXIF timestamps, so the
test proves the GIF frames play in true chronological order.

## Ink animation (artistic MP4 from a PDF art book)

`ink_extract_assets.py` + `ink_render.py` turn a scanned art-book PDF into a
monochrome 9:16 animation: scanned pages with slow Ken Burns zooms, ink-blot
wipe transitions, film grain + vignette, and kinetic text taken from the
book ("We could be...", "It could be...", "We expect to call...", A-Z).

```bash
pip install -r requirements.txt
# place the PDF next to the scripts, then:
python ink_extract_assets.py --pdf nOlBHcsP-20261114073123_001-2.pdf   # -> ink_assets/pages/
python ink_render.py --w 1080 --h 1920 --fps 30 --dur 15.0 \
  --mode hybrid --text all --out nOlBHcsP-20261114073123_001-2_ink_9x16_15s.mp4
```

`--mode hybrid|pages|gen` (pages + overlays / pages only / generative), `--text all|sentences|az|none`,
`--preview 1.0,3.6,12.8` dumps full-res stills. Prebuilt output:
`nOlBHcsP-20261114073123_001-2_ink_9x16_15s.mp4` (1080x1920, 30 fps, 15 s, h264/yuv420p).
