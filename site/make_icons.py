"""Generates the app icon set: brass bell on a night-blue rounded square with a dawn-gradient
bottom edge. Run once, commit the output.

    python site/make_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

BG = (14, 20, 27, 255)        # --bg
BRASS = (217, 164, 65, 255)   # --brass
BRASS_LIGHT = (240, 195, 106, 255)
LINE = (22, 32, 43, 255)

OUT_DIR = Path(__file__).resolve().parent / "icons"


def _horizon_gradient(width, height):
    """Thin left-to-right gradient bar: --line -> muted slate -> brass -> light brass."""
    stops = [
        (0.00, (22, 32, 43)),
        (0.45, (58, 74, 92)),
        (0.82, BRASS[:3]),
        (1.00, BRASS_LIGHT[:3]),
    ]
    bar = Image.new("RGBA", (width, height))
    for x in range(width):
        t = x / max(1, width - 1)
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1 or i == len(stops) - 2:
                local_t = 0 if t1 == t0 else (t - t0) / (t1 - t0)
                local_t = max(0.0, min(1.0, local_t))
                r = int(c0[0] + (c1[0] - c0[0]) * local_t)
                g = int(c0[1] + (c1[1] - c0[1]) * local_t)
                b = int(c0[2] + (c1[2] - c0[2]) * local_t)
                for y in range(height):
                    bar.putpixel((x, y), (r, g, b, 255))
                break
    return bar


def _draw_bell(draw: ImageDraw.ImageDraw, cx, cy, scale):
    """Simple two-arc bell silhouette, brass on transparent/bg."""
    body_w = scale * 0.62
    body_h = scale * 0.56
    top_y = cy - scale * 0.30

    # Bell body: a rounded dome (pieslice) plus flared base (trapezoid-ish via polygon)
    dome_box = [cx - body_w / 2, top_y, cx + body_w / 2, top_y + body_h]
    draw.pieslice(dome_box, 180, 360, fill=BRASS)
    draw.rectangle([cx - body_w / 2, top_y + body_h / 2, cx + body_w / 2, top_y + body_h], fill=BRASS)

    flare_top_w = body_w
    flare_bottom_w = scale * 0.92
    flare_top_y = top_y + body_h
    flare_bottom_y = flare_top_y + scale * 0.14
    draw.polygon(
        [
            (cx - flare_top_w / 2, flare_top_y),
            (cx + flare_top_w / 2, flare_top_y),
            (cx + flare_bottom_w / 2, flare_bottom_y),
            (cx - flare_bottom_w / 2, flare_bottom_y),
        ],
        fill=BRASS,
    )
    # Lip
    lip_h = scale * 0.05
    draw.rectangle(
        [cx - flare_bottom_w / 2, flare_bottom_y, cx + flare_bottom_w / 2, flare_bottom_y + lip_h],
        fill=BRASS_LIGHT,
    )
    # Clapper
    clapper_r = scale * 0.035
    draw.ellipse(
        [cx - clapper_r, flare_bottom_y + lip_h, cx + clapper_r, flare_bottom_y + lip_h + clapper_r * 2],
        fill=BRASS_LIGHT,
    )
    # Top loop
    loop_r = scale * 0.055
    draw.ellipse([cx - loop_r, top_y - loop_r * 1.3, cx + loop_r, top_y + loop_r * 0.7], outline=BRASS, width=max(2, int(scale * 0.03)))


def _make_icon(size, padding_frac=0.0):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = int(size * 0.22)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BG)

    bar_h = max(2, int(size * 0.045))
    bar = _horizon_gradient(size, bar_h)
    mask = Image.new("L", (size, bar_h), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rectangle([0, 0, size, bar_h], fill=255)
    img.paste(bar, (0, size - bar_h), mask)

    content_scale = size * (1 - padding_frac * 2)
    _draw_bell(draw, size / 2, size / 2 - size * 0.03, content_scale * 0.62)

    # Re-clip to rounded rect
    clip_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(clip_mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), clip_mask)
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    icon_192 = _make_icon(192, padding_frac=0.06)
    icon_192.save(OUT_DIR / "icon-192.png")

    icon_512 = _make_icon(512, padding_frac=0.20)  # ~20% safe padding for maskable
    icon_512.save(OUT_DIR / "icon-512.png")

    apple_touch = _make_icon(180, padding_frac=0.06)
    apple_touch.save(OUT_DIR / "apple-touch-icon.png")

    favicon_sizes = [16, 32, 48]
    favicon_imgs = [_make_icon(s, padding_frac=0.04) for s in favicon_sizes]
    favicon_imgs[0].save(OUT_DIR / "favicon.ico", sizes=[(s, s) for s in favicon_sizes])

    print(f"Wrote icons to {OUT_DIR}")


if __name__ == "__main__":
    main()
