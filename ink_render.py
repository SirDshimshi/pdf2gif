import argparse
import io
import math
import os
import warnings

warnings.filterwarnings("ignore")

import numpy as np
from PIL import Image, ImageFilter
import imageio.v2 as imageio
import pymupdf

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ink_assets", "pages")


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def load_page(n):
    img = Image.open(f"{ASSETS}/page-{n:02d}.png").convert("L")
    return img


class Grain:
    def __init__(self, w, h, seed=7, tiles=8):
        rng = np.random.default_rng(seed)
        self.tiles = [(rng.integers(0, 256, size=(h // 2, w // 2), dtype=np.uint8)) for _ in range(tiles)]
        self.w, self.h = w, h

    def apply(self, arr, i):
        g = self.tiles[i % len(self.tiles)]
        g = np.asarray(Image.fromarray(g).resize((self.w, self.h), Image.BILINEAR), dtype=np.int16)
        out = arr.astype(np.int16) + (g - 128)[:, :, None] * 0.055
        return np.clip(out, 0, 255).astype(np.uint8)


def make_vignette(w, h, strength=0.35):
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    v = 1 - strength * np.clip(r - 0.55, 0, 1) ** 1.6
    return v


def blot_field(w, h, cx, cy, seed, rough=0.22):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    dx = (xx - cx) / (w / 2)
    dy = (yy - cy) / (h / 2)
    r = np.sqrt(dx * dx + dy * dy)
    theta = np.arctan2(dy, dx)
    n = np.zeros_like(r)
    for k in range(2, 9):
        n += (1.0 / k) * np.sin(k * theta + rng.uniform(0, 2 * math.pi)) * rng.uniform(0.4, 1.0)
    n /= 2.2
    return r + rough * n


def paper_bg(w, h, base=232, seed=3):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    tex = 1 + 0.03 * np.sin(yy * 0.11 + rng.uniform(0, 6)) + rng.normal(0, 0.012, size=(h, w))
    v = np.clip(base * tex, 0, 255).astype(np.uint8)
    img = Image.fromarray(v, "L").convert("RGB")
    return img


def render_text_png(text, size, tracking=0.0, font="tiro", color=(20, 20, 20), pad=80):
    scale = 2
    est_w = int(len(text) * size * 0.62 * (1 + tracking) * scale) + pad * 2
    est_h = int(size * 1.6 * scale) + pad * 2
    doc = pymupdf.open()
    page = doc.new_page(width=est_w, height=est_h)
    page.insert_text((pad, pad + size * scale * 0.8), text, fontname=font,
                     fontsize=size * scale, color=tuple(c / 255 for c in color))
    pix = page.get_pixmap(alpha=True)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
    doc.close()
    return img


def paste_text(base, text_img, cx, cy, alpha, width_scale=1.0):
    if alpha <= 0 or width_scale <= 0:
        return
    tw = max(1, int(text_img.width * width_scale))
    th = max(1, int(text_img.height * tw / text_img.width))
    t = text_img.resize((tw, th), Image.LANCZOS)
    a = t.split()[3].point(lambda p: int(p * min(1.0, alpha)))
    t.putalpha(a)
    base.alpha_composite(t, (int(cx - tw / 2), int(cy - th / 2)))


def text_with_halo(text, size, tracking, color=(18, 18, 18)):
    img = render_text_png(text, size, tracking, color=color)
    halo = render_text_png(text, size, tracking, color=(240, 240, 240))
    halo = halo.filter(ImageFilter.GaussianBlur(6))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(halo)
    out.alpha_composite(img)
    return out


class PageScene:
    def __init__(self, w, h, page_no, z0=1.0, z1=1.12, cx0=0.5, cy0=0.45, cx1=0.5, cy1=0.55, text=None):
        self.w, self.h = w, h
        self.img = load_page(page_no)
        self.pw, self.ph = self.img.size
        self.cover = max(w / self.pw, h / self.ph)
        self.z0, self.z1 = z0, z1
        self.cx0, self.cy0, self.cx1, self.cy1 = cx0, cy0, cx1, cy1
        self.text = text
        self.text_img = text_with_halo(text, 58, 0.06) if text else None

    def frame(self, t, dur):
        u = ease(t / dur)
        z = self.z0 + (self.z1 - self.z0) * u
        cx = self.cx0 + (self.cx1 - self.cx0) * u
        cy = self.cy0 + (self.cy1 - self.cy0) * u
        s = self.cover * z
        cw, ch = self.w / s, self.h / s
        left = int(cx * self.pw - cw / 2)
        top = int(cy * self.ph - ch / 2)
        left = max(0, min(self.pw - int(cw), left))
        top = max(0, min(self.ph - int(ch), top))
        crop = self.img.crop((left, top, left + int(cw), top + int(ch))).resize((self.w, self.h), Image.BICUBIC)
        base = crop.convert("RGB").convert("RGBA")
        if self.text and self.text_img:
            a = ease_out(min(1.0, t / 0.7)) * (1 - ease_out(max(0.0, (t - (dur - 0.6)) / 0.5)))
            paste_text(base, self.text_img, self.w / 2, self.h * 0.82, a, width_scale=1.14 - 0.14 * ease_out(t / 1.0))
        return base


class BlotScene:
    def __init__(self, w, h, seed, mode="in", base=232):
        self.w, self.h = w, h
        self.field = blot_field(w, h, w / 2, h * 0.44, seed)
        self.mode = mode
        self.paper = paper_bg(w, h, base=base, seed=seed + 1)

    def frame(self, t, dur):
        u = ease(t / dur)
        if self.mode == "in":
            m = self.field < 0.12 + 0.85 * u
        else:
            m = self.field < 0.97 - 0.85 * ease_out(u)
        base = self.paper.convert("RGBA")
        black = Image.new("RGBA", (self.w, self.h), (12, 12, 12, 255))
        mask_img = Image.fromarray((m * 255).astype(np.uint8), "L")
        base.paste(black, (0, 0), mask_img)
        return base


class TextScene:
    def __init__(self, w, h, kind, seed=11, base=236):
        self.w, self.h = w, h
        self.kind = kind
        self.paper = paper_bg(w, h, base=base, seed=seed)
        rng = np.random.default_rng(seed)
        if kind == "az":
            self.letters = [render_text_png(ch, 64, 0.0) for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
            self.xs = [w / 2 + rng.uniform(-30, 30) for _ in self.letters]
            self.ys = [h * 0.12 + i * (h * 0.76 / 25) for i in range(26)]
        else:
            self.img = text_with_halo(kind, 72, 0.05)

    def frame(self, t, dur):
        base = self.paper.convert("RGBA")
        if self.kind == "az":
            for i, img in enumerate(self.letters):
                a = ease_out(max(0.0, min(1.0, (t - i * 0.032) / 0.3))) * (1 - ease_out(max(0.0, (t - (dur - 0.8)) / 0.6)))
                if a > 0:
                    paste_text(base, img, self.xs[i], self.ys[i], a)
        else:
            a = ease_out(min(1.0, t / 1.0)) * (1 - ease_out(max(0.0, (t - (dur - 0.9)) / 0.7)))
            paste_text(base, self.img, self.w / 2, self.h * 0.5, a, width_scale=1.18 - 0.18 * ease_out(t / 1.1))
        return base


def build_scenes(w, h, mode, text_mode):
    scenes = []
    add_text = text_mode in ("all", "sentences")
    add_az = text_mode in ("all", "az")
    if mode in ("gen", "hybrid"):
        scenes.append(("blot", BlotScene(w, h, seed=42, mode="in"), 2.0))
    pages = [21, 17, 19, 13, 6, 25] if mode == "hybrid" else []
    texts = ["We could be...", "It could be...", "We expect to call..."] if add_text else [None] * 3
    if mode == "hybrid":
        for i, p in enumerate(pages[:3]):
            scenes.append(("page", PageScene(w, h, p, text=texts[i] if i < len(texts) else None), 2.5))
    else:
        for i in range(3):
            scenes.append(("blot", BlotScene(w, h, seed=100 + i, mode="in" if i % 2 == 0 else "out"), 2.5))
    if mode == "hybrid":
        scenes.append(("page", PageScene(w, h, pages[3] if len(pages) > 3 else 13), 2.5))
        scenes.append(("page", PageScene(w, h, pages[4] if len(pages) > 4 else 6), 2.5))
    if add_az:
        scenes.append(("text", TextScene(w, h, "az"), 3.2))
    if mode in ("gen", "hybrid"):
        scenes.append(("blot", BlotScene(w, h, seed=77, mode="out"), 1.3))
    return scenes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--w", type=int, default=1080)
    ap.add_argument("--h", type=int, default=1920)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--dur", type=float, default=15.0)
    ap.add_argument("--mode", default="hybrid", choices=["hybrid", "pages", "gen"])
    ap.add_argument("--text", default="all", choices=["all", "sentences", "az", "none"])
    ap.add_argument("--out", default="out/draft.mp4")
    ap.add_argument("--trans", type=float, default=0.8)
    ap.add_argument("--preview", default="")
    ap.add_argument("--assets", default=ASSETS)
    args = ap.parse_args()
    globals()["ASSETS"] = args.assets

    w, h, fps = args.w, args.h, args.fps
    scenes = build_scenes(w, h, args.mode, args.text)
    total = sum(d for _, _, d in scenes)
    scale = args.dur / total
    scenes = [(k, s, d * scale) for k, s, d in scenes]
    total = sum(d for _, _, d in scenes)
    print(f"scenes: {[(k, round(d,2)) for k, _, d in scenes]} total={total:.2f}s")

    grain = Grain(w, h)
    vig = make_vignette(w, h)
    T = args.trans

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    writer = imageio.get_writer(args.out, fps=fps, codec="libx264",
                                 quality=None, macro_block_size=None,
                                 ffmpeg_params=["-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"])
    nframes = int(round(args.dur * fps))
    previews = [float(x) for x in args.preview.split(",") if x]

    starts = []
    acc = 0.0
    for _, _, d in scenes:
        starts.append(acc)
        acc += d

    def scene_at(g):
        for i in range(len(scenes) - 1, -1, -1):
            if g >= starts[i] - 1e-9:
                return i, g - starts[i]
        return 0, g

    for fi in range(nframes):
        g = fi / fps
        i, t = scene_at(g)
        kind, scene, dur = scenes[i]
        img = scene.frame(t, dur)
        if t > dur - T and i + 1 < len(scenes):
            u = (t - (dur - T)) / T
            kind2, scene2, dur2 = scenes[i + 1]
            img2 = scene2.frame(0.0 + u * T, dur2)
            f = blot_field(w, h, w / 2, h * 0.45, seed=900 + i)
            if u < 0.5:
                m = (f < 0.1 + 1.1 * (u * 2)) 
                black = Image.new("RGBA", (w, h), (10, 10, 10, 255))
                mask = Image.fromarray((m * 255).astype(np.uint8), "L")
                img.paste(black, (0, 0), mask)
            else:
                m = (f > 1.2 - 1.1 * ((u - 0.5) * 2))
                black = Image.new("RGBA", (w, h), (10, 10, 10, 255))
                mask = Image.fromarray((m * 255).astype(np.uint8), "L")
                img2.paste(black, (0, 0), mask)
                img = img2
        arr = np.asarray(img.convert("RGB"), dtype=np.float32) * vig[:, :, None]
        arr = grain.apply(arr.astype(np.uint8), fi)
        arr = np.clip(arr * (1 + 0.012 * np.sin(fi * 0.7)), 0, 255).astype(np.uint8)
        writer.append_data(arr)
        if previews and any(abs(g - p) < 1.0 / fps for p in previews):
            Image.fromarray(arr).save(f"{os.path.dirname(args.out)}/preview_{int(g*10):03d}.png")
        if fi % 60 == 0:
            print(f"frame {fi}/{nframes} t={g:.2f}s")
    writer.close()
    print("wrote", args.out)


if __name__ == "__main__":
    main()
