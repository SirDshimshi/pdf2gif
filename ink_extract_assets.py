import argparse
import pymupdf
from PIL import Image

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default="nOlBHcsP-20261114073123_001-2.pdf")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--out", default="ink_assets/pages")
    args = ap.parse_args()

    doc = pymupdf.open(args.pdf)
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=args.dpi, colorspace=pymupdf.csGRAY)
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        w, h = img.size
        m = int(0.02 * min(w, h))
        img = img.crop((m, m, w - m, h - int(0.035 * h)))
        img.save(f"{args.out}/page-{i+1:02d}.png")
        if (i + 1) % 10 == 0:
            print(f"extracted {i+1}/{len(doc)}")
    print("done", len(doc), "pages at", args.dpi, "dpi")


if __name__ == "__main__":
    main()
