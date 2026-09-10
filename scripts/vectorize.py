#!/usr/bin/env python3
"""
vectorize.py - Convert raster logos / icons / line art into clean SVG.

A standalone command-line image vectorizer (raster -> SVG) in the spirit of
vectorizer.ai, built on the VTracer engine (https://github.com/visioncortex/vtracer)
with Pillow-based preprocessing tuned for flat-colour graphics.

Best for: logos, icons, line art, clipart - flat regions of solid colour with
crisp edges. It is NOT meant for photographs (those should stay raster).

Examples
--------
    # Single logo with the default 'logo' preset:
    python scripts/vectorize.py logo.png

    # Crisp black-and-white line art, explicit output path:
    python scripts/vectorize.py sketch.png --preset lineart -o sketch.svg

    # Reduce to 8 colours, upscale 2x, and write a PNG preview to eyeball:
    python scripts/vectorize.py icon.png --colors 8 --upscale 2 --preview

    # Batch every image in a folder into ./out:
    python scripts/vectorize.py ./assets -o ./out --preset icon

    # Crispest B/W line art via the potrace engine (upscale helps small art):
    python scripts/vectorize.py sketch.png --engine potrace --upscale 3 -o sketch.svg

    # White line-art on a dark background -> inverted, tinted output:
    python scripts/vectorize.py glyph.png --engine potrace --invert --fillcolor "#16181a"

    # Transparent line-art glyph (e.g. an unselected toolbar icon) -> potrace:
    python scripts/vectorize.py pen_unselected.png --preset glyph

Requirements: vtracer, Pillow.  Optional: potrace.exe (for --engine potrace),
PyQt6 (only for --preview).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import vtracer
except ImportError:
    sys.exit("error: vtracer is not installed.  Install it with:  pip install vtracer")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}

# --- Presets: tuned starting points for different flat-colour artwork --------
# Keys map onto VTracer's tracing parameters, plus two preprocessing knobs
# ('colors', 'upscale') handled by Pillow before tracing.  Override any field
# from the command line (e.g. --filter-speckle 20) to fine-tune a preset.
PRESETS = {
    # Clean company logos / flat illustrations: merge anti-aliasing, despeckle.
    "logo": dict(colormode="color", mode="spline", filter_speckle=8,
                 color_precision=6, layer_difference=16, corner_threshold=60,
                 length_threshold=4.0, splice_threshold=45, path_precision=3,
                 colors=16, upscale=1.0),
    # Small UI icons: heavier despeckle + upscale for smoother curves.
    "icon": dict(colormode="color", mode="spline", filter_speckle=12,
                 color_precision=6, layer_difference=20, corner_threshold=70,
                 length_threshold=4.0, splice_threshold=45, path_precision=3,
                 colors=12, upscale=2.0),
    # Black-and-white line art / sketches / signatures.
    "lineart": dict(colormode="binary", mode="spline", filter_speckle=6,
                    color_precision=6, layer_difference=16, corner_threshold=60,
                    length_threshold=4.0, splice_threshold=45, path_precision=3,
                    colors=None, upscale=1.0),
    # Posterised / sticker look: few flat colours, polygonal edges.
    "poster": dict(colormode="color", mode="polygon", filter_speckle=16,
                   color_precision=5, layer_difference=28, corner_threshold=80,
                   length_threshold=6.0, splice_threshold=45, path_precision=2,
                   colors=8, upscale=1.0),
    # Maximum fidelity: keep detail, many layers (larger files).
    "detailed": dict(colormode="color", mode="spline", filter_speckle=4,
                     color_precision=8, layer_difference=8, corner_threshold=45,
                     length_threshold=4.0, splice_threshold=45, path_precision=5,
                     colors=None, upscale=1.0),
    # Transparent / line-art glyphs (e.g. unselected toolbar icons): trace the
    # alpha channel with potrace for the crispest single-colour curves.
    "glyph": dict(engine="potrace", trace_channel="auto", invert=True,
                  trim_bg=True, autocrop=True, despeckle_frac=0.05,
                  filter_speckle=4, alphamax=1.0, turnpolicy="minority",
                  fillcolor="#f5f5f7"),
}

# VTracer keyword arguments (a preset's keys minus our preprocessing keys).
_VTRACER_KEYS = ("colormode", "mode", "filter_speckle", "color_precision",
                 "layer_difference", "corner_threshold", "length_threshold",
                 "splice_threshold", "path_precision")

# potrace turn-policy choices (how it resolves ambiguous turns when tracing).
POTRACE_TURNPOLICIES = ("black", "white", "left", "right",
                        "minority", "majority", "random")
# Fallback location for a bundled potrace.exe when it is not on PATH.
_BUNDLED_POTRACE = Path(__file__).resolve().parent.parent / "tools" / "potrace"


def human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} MB"


def preprocess(src: Path, *, colors, upscale, threshold, bg):
    """Optional Pillow preprocessing. Returns (path, is_temp_file)."""
    need = (colors is not None) or (upscale and upscale != 1.0) \
        or (threshold is not None) or (bg is not None)
    if not need:
        return str(src), False

    from PIL import Image, ImageColor

    img = Image.open(src).convert("RGBA")

    if bg is not None:
        rgba = ImageColor.getcolor(bg, "RGBA")
        background = Image.new("RGBA", img.size, rgba)
        img = Image.alpha_composite(background, img)

    if upscale and upscale != 1.0:
        w, h = img.size
        img = img.resize((max(1, round(w * upscale)), max(1, round(h * upscale))),
                         Image.LANCZOS)

    if threshold is not None:
        gray = img.convert("L")
        img = gray.point(lambda p: 255 if p >= threshold else 0).convert("RGBA")
    elif colors is not None:
        alpha = img.getchannel("A")
        quant = img.convert("RGB").quantize(colors=max(2, colors)).convert("RGB")
        quant.putalpha(alpha)
        img = quant

    fd, tmp = tempfile.mkstemp(suffix=".png", prefix="vectorize_")
    os.close(fd)
    img.save(tmp)
    return tmp, True


def find_potrace(explicit: str | None = None) -> str | None:
    """Locate potrace: explicit path, $POTRACE_BIN, a bundled copy, then PATH."""
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("POTRACE_BIN"):
        candidates.append(os.environ["POTRACE_BIN"])
    candidates.append(str(_BUNDLED_POTRACE / "potrace.exe"))
    candidates.append(str(_BUNDLED_POTRACE / "potrace"))
    candidates.append("potrace")  # bare name -> resolved on PATH
    for cand in candidates:
        if Path(cand).is_file():
            return cand
        found = shutil.which(cand)
        if found:
            return found
    return None


def _trace_vtracer(src: Path, dst: Path, params: dict) -> None:
    """Trace with the VTracer engine (colour or binary)."""
    p = dict(params)
    colors = p.pop("colors", None)
    upscale = p.pop("upscale", 1.0)
    threshold = p.pop("threshold", None)
    bg = p.pop("bg", None)

    work, is_temp = preprocess(src, colors=colors, upscale=upscale,
                               threshold=threshold, bg=bg)
    base = PRESETS["logo"]  # fall back for keys a non-vtracer preset may omit
    try:
        vtracer.convert_image_to_svg_py(
            str(work), str(dst),
            hierarchical="stacked", max_iterations=10,
            **{k: p.get(k, base[k]) for k in _VTRACER_KEYS},
        )
    finally:
        if is_temp:
            try:
                os.remove(work)
            except OSError:
                pass


def _drop_small_components(bw, frac):
    """Remove black blobs smaller than frac x the largest one (needs numpy+scipy)."""
    try:
        import numpy as np
        from scipy import ndimage
    except ImportError:
        print("warning: --despeckle-frac needs numpy+scipy; leaving specks in.",
              file=sys.stderr)
        return bw
    from PIL import Image
    labels, count = ndimage.label(np.asarray(bw) == 0)  # black = traced figure
    if count <= 1:
        return bw
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0  # ignore the white background
    kept = (sizes >= frac * sizes.max())[labels]
    return Image.fromarray(np.where(kept, 0, 255).astype("uint8"), "L").convert("1")


def _trace_potrace(src: Path, dst: Path, params: dict, potrace_bin: str) -> None:
    """Trace with potrace: Pillow makes a clean 1-bit bitmap, potrace fits curves.

    Transparent line-art (e.g. unselected toolbar glyphs) is traced from the
    ALPHA channel, so the artwork's own colour does not matter; opaque images use
    a luminance threshold instead (with --invert for light-on-dark art).
    """
    from PIL import Image, ImageColor, ImageDraw

    upscale = params.get("upscale") or 1.0
    threshold = params.get("threshold")
    invert = bool(params.get("invert"))
    bg = params.get("bg") or "#ffffff"
    channel = params.get("trace_channel") or "auto"
    trim_bg = bool(params.get("trim_bg"))
    autocrop = bool(params.get("autocrop"))
    despeckle_frac = float(params.get("despeckle_frac") or 0.0)
    turdsize = int(params.get("filter_speckle") or 2)
    alphamax = params.get("alphamax")
    opttolerance = params.get("opttolerance")
    turnpolicy = params.get("turnpolicy") or "minority"
    fillcolor = params.get("fillcolor") or "#000000"

    img = Image.open(src).convert("RGBA")
    if upscale and upscale != 1.0:
        w, h = img.size
        img = img.resize((max(1, round(w * upscale)), max(1, round(h * upscale))),
                         Image.LANCZOS)
    if channel == "auto":
        channel = "alpha" if img.getchannel("A").getextrema()[0] < 250 else "luma"

    # potrace traces BLACK pixels. Build a 1-bit bitmap whose black = the artwork.
    thr = 128 if threshold is None else threshold
    if channel == "alpha":
        # Opaque pixels are the figure; alpha already isolates line-art cleanly,
        # so --invert / --trim-bg do not apply here.
        bw = img.getchannel("A").point(lambda v: 0 if v >= thr else 255).convert("1")
    else:
        gray = Image.alpha_composite(
            Image.new("RGBA", img.size, ImageColor.getcolor(bg, "RGBA")), img).convert("L")
        if trim_bg:
            # Flood the border-connected surround to the background tone so it is
            # not traced (isolates a glyph that sits inside a filled button).
            gray = gray.copy()
            fill = 0 if invert else 255
            for seed in ((0, 0), (gray.width - 1, 0), (0, gray.height - 1),
                         (gray.width - 1, gray.height - 1)):
                ImageDraw.floodfill(gray, seed, fill, thresh=90)
        bw = gray.point(lambda v: 255 if v >= thr else 0).convert("1")
        if invert:
            bw = bw.point(lambda v: 0 if v else 255).convert("1")

    if despeckle_frac > 0:
        bw = _drop_small_components(bw, despeckle_frac)

    if autocrop:
        # Crop tight to the traced figure so the SVG viewBox hugs the artwork.
        figure = bw.convert("L").point(lambda v: 255 if v < 128 else 0)
        box = figure.getbbox()
        if box:
            span = max(box[2] - box[0], box[3] - box[1])
            pad = max(2, round(span * 0.04))
            bw = bw.crop((max(0, box[0] - pad), max(0, box[1] - pad),
                          min(bw.width, box[2] + pad), min(bw.height, box[3] + pad)))

    fd, tmp = tempfile.mkstemp(suffix=".pbm", prefix="vectorize_")
    os.close(fd)
    bw.save(tmp)
    try:
        cmd = [potrace_bin, "--svg", "-o", str(dst),
               "--turdsize", str(turdsize),
               "--turnpolicy", turnpolicy,
               "--color", fillcolor]
        if alphamax is not None:
            cmd += ["--alphamax", str(alphamax)]
        if opttolerance is not None:
            cmd += ["--opttolerance", str(opttolerance)]
        cmd.append(tmp)
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError("potrace failed: "
                               + (res.stderr.strip() or res.stdout.strip() or "unknown error"))
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def vectorize(src: Path, dst: Path, params: dict, engine: str = "vtracer",
              potrace_bin: str | None = None) -> dict:
    """Trace one image to SVG with the chosen engine. Returns a stats dict."""
    t0 = time.time()
    if engine == "potrace":
        _trace_potrace(src, dst, params, potrace_bin)
    else:
        _trace_vtracer(src, dst, params)
    dt = time.time() - t0

    svg = dst.read_text(encoding="utf-8")
    return {
        "ms": dt * 1000,
        "src_bytes": src.stat().st_size,
        "dst_bytes": dst.stat().st_size,
        "paths": svg.count("<path"),
    }


def render_preview(svg_path: Path, png_path: Path, size: int = 512) -> bool:
    """Rasterise an SVG to PNG via PyQt6/QtSvg (offscreen). Returns success."""
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QGuiApplication, QImage, QPainter
        from PyQt6.QtSvg import QSvgRenderer
    except Exception:
        return False

    _ = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    renderer = QSvgRenderer(str(svg_path))
    ds = renderer.defaultSize()
    w, h = ds.width(), ds.height()
    if w <= 0 or h <= 0:
        w = h = size
    scale = size / max(w, h)
    image = QImage(QSize(round(w * scale), round(h * scale)),
                   QImage.Format.Format_ARGB32)
    image.fill(0)  # transparent
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    return bool(image.save(str(png_path)))


def collect_inputs(paths):
    """Expand files and directories into a flat list of image files."""
    out = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            out.extend(sorted(f for f in p.iterdir()
                              if f.suffix.lower() in IMAGE_EXTS))
        elif p.is_file():
            out.append(p)
        else:
            print(f"warning: not found, skipping: {p}", file=sys.stderr)
    return out


def resolve_output(src: Path, out_arg, many: bool) -> Path:
    """Decide the .svg output path for a given source image."""
    if out_arg is None:
        return src.with_suffix(".svg")
    out = Path(out_arg)
    # Treat as a directory if it is one, looks like one, or we have many inputs.
    is_dir = out.is_dir() or many or out_arg.endswith(("/", "\\")) or out.suffix == ""
    if is_dir:
        out.mkdir(parents=True, exist_ok=True)
        return out / (src.stem + ".svg")
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="vectorize.py",
        description="Convert raster logos / icons / line art to clean SVG (VTracer).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Presets: " + ", ".join(PRESETS) + ".  Any knob below overrides the preset.",
    )
    ap.add_argument("inputs", nargs="+", help="image file(s) or folder(s) to vectorize")
    ap.add_argument("-o", "--output", help="output .svg file, or a folder for batch/many")
    ap.add_argument("--preset", choices=list(PRESETS), default="logo",
                    help="tuning preset (default: logo; ignored by --engine potrace)")
    ap.add_argument("--engine", choices=["vtracer", "potrace"], default=None,
                    help="tracing engine: vtracer (colour) or potrace (crisp B/W "
                         "line art); default vtracer, or the preset's own engine")

    g = ap.add_argument_group("overrides (optional; default = preset value)")
    g.add_argument("--bw", action="store_true",
                   help="black-and-white mode (colormode=binary)")
    g.add_argument("--mode", choices=["spline", "polygon", "none"],
                   help="curve fitting: spline=smooth, polygon=straight, none=pixel")
    g.add_argument("--colors", type=int,
                   help="pre-quantize to N colours before tracing (merges anti-aliasing)")
    g.add_argument("--upscale", type=float, help="scale image up by this factor first")
    g.add_argument("--threshold", type=int, metavar="0-255",
                   help="pre-binarize at this grey level (implies a B/W look)")
    g.add_argument("--bg", help="flatten transparency onto this colour, e.g. white or #ffffff")
    g.add_argument("--filter-speckle", type=int, dest="filter_speckle",
                   help="discard patches smaller than N px (despeckle; higher=cleaner)")
    g.add_argument("--color-precision", type=int, dest="color_precision",
                   help="colour bits kept (lower=fewer layers)")
    g.add_argument("--layer-difference", type=int, dest="layer_difference",
                   help="min colour delta between layers (higher=fewer layers)")
    g.add_argument("--corner-threshold", type=int, dest="corner_threshold",
                   help="angle (deg) below which a corner is kept sharp")
    g.add_argument("--length-threshold", type=float, dest="length_threshold",
                   help="min segment length 3.5-10 (higher=simpler)")
    g.add_argument("--splice-threshold", type=int, dest="splice_threshold",
                   help="angle (deg) at which splines are spliced")
    g.add_argument("--path-precision", type=int, dest="path_precision",
                   help="decimal places in path coordinates")

    pt = ap.add_argument_group("potrace engine (used with --engine potrace)")
    pt.add_argument("--trace-channel", choices=["auto", "alpha", "luma"],
                    dest="trace_channel",
                    help="what to trace: alpha (transparent art), luma "
                         "(bright/dark), auto (default)")
    pt.add_argument("--invert", action="store_true",
                    help="trace light-on-dark art (e.g. white line-art on a dark bg)")
    pt.add_argument("--trim-bg", action="store_true", dest="trim_bg",
                    help="drop the border-connected background (isolate a glyph "
                         "inside a filled button)")
    pt.add_argument("--autocrop", action="store_true",
                    help="crop the SVG viewBox tight to the traced artwork")
    pt.add_argument("--despeckle-frac", type=float, dest="despeckle_frac",
                    help="drop disconnected blobs smaller than this fraction of the "
                         "largest, e.g. 0.05 (clears edge lines / watermarks; needs scipy)")
    pt.add_argument("--alphamax", type=float,
                    help="corner smoothing 0=sharp .. 1.33=round (potrace default 1.0)")
    pt.add_argument("--opttolerance", type=float,
                    help="curve optimisation tolerance (potrace default 0.2)")
    pt.add_argument("--turnpolicy", choices=POTRACE_TURNPOLICIES,
                    help="resolve ambiguous turns (potrace default minority)")
    pt.add_argument("--fillcolor", help="SVG fill colour for the shape (default #000000)")
    pt.add_argument("--potrace-bin", dest="potrace_bin",
                    help="path to potrace.exe (else $POTRACE_BIN, PATH, or tools/potrace/)")

    ap.add_argument("--preview", action="store_true",
                    help="also write <out>.preview.png (rasterised via PyQt6) to eyeball fidelity")
    ap.add_argument("-q", "--quiet", action="store_true", help="only print errors")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    # Start from the preset, then apply any explicitly-provided overrides.
    params = dict(PRESETS[args.preset])
    engine = args.engine or params.get("engine", "vtracer")
    overridable = ("mode", "colors", "upscale", "threshold", "bg", "filter_speckle",
                   "color_precision", "layer_difference", "corner_threshold",
                   "length_threshold", "splice_threshold", "path_precision",
                   "alphamax", "opttolerance", "turnpolicy", "fillcolor",
                   "trace_channel", "despeckle_frac")
    for key in overridable:
        val = getattr(args, key, None)
        if val is not None:
            params[key] = val
    if args.invert:
        params["invert"] = True
    if args.trim_bg:
        params["trim_bg"] = True
    if args.autocrop:
        params["autocrop"] = True
    if args.bw:
        params["colormode"] = "binary"

    potrace_bin = None
    if engine == "potrace":
        potrace_bin = find_potrace(args.potrace_bin)
        if not potrace_bin:
            print("error: potrace executable not found. Install it and add it to "
                  "PATH, set $POTRACE_BIN, pass --potrace-bin PATH, or place "
                  f"potrace.exe in {_BUNDLED_POTRACE}.\n"
                  "       Windows build: https://potrace.sourceforge.net/#downloading",
                  file=sys.stderr)
            return 2

    images = collect_inputs(args.inputs)
    if not images:
        print("error: no input images found.", file=sys.stderr)
        return 2
    many = len(images) > 1

    failures = 0
    for src in images:
        dst = resolve_output(src, args.output, many)
        try:
            stats = vectorize(src, dst, params, engine, potrace_bin)
        except Exception as exc:  # noqa: BLE001 - report and continue the batch
            failures += 1
            print(f"FAILED  {src.name}: {exc}", file=sys.stderr)
            continue

        if args.preview:
            preview = dst.with_suffix(".preview.png")
            if not render_preview(dst, preview):
                print(f"  (preview skipped - PyQt6 unavailable)", file=sys.stderr)

        if not args.quiet:
            ratio = stats["dst_bytes"] / stats["src_bytes"] if stats["src_bytes"] else 0
            tag = args.preset + "/potrace" if engine == "potrace" \
                else args.preset + ("/bw" if args.bw else "")
            print(f"{src.name}  ->  {dst.name}   [{tag}]  {stats['paths']} paths  "
                  f"{human_bytes(stats['src_bytes'])} -> {human_bytes(stats['dst_bytes'])} "
                  f"({ratio*100:.0f}%)  {stats['ms']:.0f} ms")

    if not args.quiet and many:
        print(f"\nDone: {len(images) - failures}/{len(images)} converted.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
