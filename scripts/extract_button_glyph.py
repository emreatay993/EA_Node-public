#!/usr/bin/env python3
"""
extract_button_glyph.py - Isolate the colour glyph from a toolbar-button screenshot.

The Writing Tools benchmark PNGs are whole buttons: a page surround, a coloured
button background (teal when selected), the glyph, a dropdown chevron, and a thin
dark crop border. This:
  1. floods away the page surround (from the four corners),
  2. chroma-keys the dominant remaining colour (the button background),
  3. drops components that touch the edge or span the whole image (the crop frame),
  4. keeps the largest remaining component (the glyph - which drops the chevron),
  5. erodes the anti-aliased fringe and crops tight,
then writes a transparent-background PNG ready to feed to `vectorize.py`.

    python scripts/extract_button_glyph.py icons/benchmark/pen.png out/pen.png
    python scripts/vectorize.py out/pen.png --preset logo -o pen_selected.svg

Requires: Pillow, numpy, scipy.
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

_SENTINEL = (1, 2, 3)  # marks flood-filled background


def extract(src, dst, thresh=48, button_thresh=80, defringe=1, pad=0.04,
            ink_out=None, ink_thresh=90, ink_luma=None):
    im = Image.open(src).convert("RGBA")
    w, h = im.size

    # 1) Remove the page surround (flood from the four corners).
    work = im.convert("RGB")
    for seed in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        ImageDraw.floodfill(work, seed, _SENTINEL, thresh=thresh)
    arr = np.asarray(work).astype(int)
    remaining = ~np.all(arr == _SENTINEL, axis=-1)

    # 2) Chroma-key the dominant remaining colour: the button background.
    px = arr[remaining] // 16 * 16
    dom = collections.Counter(map(tuple, px)).most_common(1)[0][0]
    button = remaining & (np.abs(arr - np.array(dom)).sum(-1) <= button_thresh)
    fg = remaining & ~button

    # 3) Drop the crop frame (components that touch an edge or span the whole
    #    image), then 4) keep the largest survivor (the glyph; chevron is smaller).
    labels, n = ndimage.label(fg)
    if n >= 1:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        for i, sl in enumerate(ndimage.find_objects(labels), start=1):
            if sl is None:
                continue
            spans = (sl[0].stop - sl[0].start) >= 0.85 * h and \
                    (sl[1].stop - sl[1].start) >= 0.85 * w
            touches = sl[0].start == 0 or sl[1].start == 0 \
                or sl[0].stop == h or sl[1].stop == w
            if spans or touches:
                sizes[i] = 0
        if sizes.max() > 0:
            fg = labels == int(sizes.argmax())
    if defringe > 0:
        fg = ndimage.binary_erosion(fg, iterations=defringe)

    # One crop box (the full glyph) shared by base + ink so the layers align.
    box = Image.fromarray((fg * 255).astype("uint8"), "L").getbbox()
    if box:
        span = max(box[2] - box[0], box[3] - box[1])
        p = max(2, round(span * pad))
        crop = (max(0, box[0] - p), max(0, box[1] - p),
                min(w, box[2] + p), min(h, box[3] + p))
    else:
        crop = (0, 0, w, h)

    def _save(mask, path, solid=None):
        out = np.zeros((h, w, 4), np.uint8) if solid else np.array(im)
        if solid is not None:
            out[mask] = solid
        else:
            out[~mask] = (0, 0, 0, 0)
        Image.fromarray(out, "RGBA").crop(crop).save(path)

    if ink_out:
        # Split the recolourable "ink" into a white silhouette to tint live in QML;
        # the base keeps the fixed structural colours (outline, nib, holder, wood).
        #
        # By default the ink is the SATURATED accent (pen blue, highlighter green,
        # tape red) - saturation is hue-independent, so it works regardless of the
        # exact accent shade. But a grey tool (the pencil's barrel + graphite tip)
        # has near-zero saturation, so for those pass --ink-luma LO HI to select a
        # LUMINANCE band instead: it grabs the mid-grey body+tip while excluding the
        # lighter wood cone and the near-black outline.
        if ink_luma is not None:
            lo, hi = ink_luma
            rgb = arr  # already int RGB of the de-surrounded image
            lum = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
            ink = fg & (lum >= lo) & (lum <= hi)
            how = f"luma {lo}-{hi}"
        else:
            sat = np.asarray(im.convert("HSV"))[..., 1].astype(int)
            ink = fg & (sat >= ink_thresh)
            how = f"sat>={ink_thresh}"
        _save(fg & ~ink, dst)
        _save(ink, ink_out, solid=(255, 255, 255, 255))
        print(f"{Path(src).name} -> {Path(dst).name} + {Path(ink_out).name} "
              f"({how}: ink {int(ink.sum())}px of {int(fg.sum())}px)")
    else:
        _save(fg, dst)
        print(f"{Path(src).name} -> {Path(dst).name}  kept={int(fg.sum())}px")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Isolate a button glyph to a transparent PNG.")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--thresh", type=int, default=48,
                    help="surround flood tolerance (sum of per-channel diffs)")
    ap.add_argument("--button-thresh", type=int, dest="button_thresh", default=80,
                    help="how close a pixel must be to the dominant button colour to drop it")
    ap.add_argument("--defringe", type=int, default=1,
                    help="erode N px to drop the anti-aliased halo (default 1)")
    ap.add_argument("--ink-out", dest="ink_out",
                    help="also write a white silhouette of the saturated accent here "
                         "(the recolourable 'ink' layer to tint live in QML)")
    ap.add_argument("--ink-thresh", dest="ink_thresh", type=int, default=90,
                    help="HSV saturation 0-255 above which a pixel is recolourable ink")
    ap.add_argument("--ink-luma", dest="ink_luma", type=int, nargs=2,
                    metavar=("LO", "HI"),
                    help="select ink by a LUMINANCE band [LO HI] (0-255) instead of "
                         "saturation - for grey tools like the pencil (body+tip), "
                         "excluding the lighter wood cone and near-black outline")
    a = ap.parse_args(argv)
    Path(a.dst).parent.mkdir(parents=True, exist_ok=True)
    extract(a.src, a.dst, thresh=a.thresh, button_thresh=a.button_thresh,
            defringe=a.defringe, ink_out=a.ink_out, ink_thresh=a.ink_thresh,
            ink_luma=tuple(a.ink_luma) if a.ink_luma else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
