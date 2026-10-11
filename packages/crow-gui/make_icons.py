#!/usr/bin/env python3
"""Regenerate crow's IDE icons from art/ into the vendored VSCodium tree.

VSCodium's own icons/build_icons.sh needs rsvg-convert/imagemagick/icns tools
and downloads VSCodium art from the network; crow builds Linux only, so this
script derives exactly the files the Linux build and the web server consume
from the committed brand art in art/. Run it after changing the art, then
commit both art/ and the generated files.
"""

import base64
import io
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
ART = ROOT / "art"
RES = ROOT / "vscodium" / "src" / "stable" / "resources"
BG = "#6553ff"  # the brand disc colour, matching art/crow-logo.png


def tile() -> Image.Image:
    return Image.open(ART / "crow-logo.png").convert("RGBA")


def write_png(size: int, dest: Path) -> None:
    tile().resize((size, size), Image.LANCZOS).save(dest, optimize=True)
    print(f"  {dest.relative_to(ROOT)}  {size}x{size}")


def write_favicon(dest: Path) -> None:
    sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    tile().save(dest, format="ICO", sizes=sizes)
    print(f"  {dest.relative_to(ROOT)}  {len(sizes)} sizes")


def write_svg(dest: Path) -> None:
    # The vector art is a white glyph on nothing; the shipped icon must carry
    # its own background or it vanishes on light desktop themes. crow's mark
    # sits on a disc (art/crow-logo.png), not a square tile, so the vector gets
    # the same inscribed circle.
    src = (ART / "crow-logo.svg").read_text()
    disc = f'  <circle cx="512" cy="512" r="512" fill="{BG}" />\n'
    marker = '<defs\n     id="defs1" />'
    assert marker in src, "unexpected art/crow-logo.svg shape"
    dest.write_text(src.replace(marker, marker + "\n" + disc, 1))
    print(f"  {dest.relative_to(ROOT)}  vector + {BG} disc")


def write_embedded_svg(dest: Path, px: int) -> None:
    # art/crow-logo.svg is a stroke-only outline that vanishes against the disc,
    # so the "vector" assets ship the brand raster inside an svg container: same
    # file shape the build expects, pixels that actually look like crow.
    img = tile().resize((px, px), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()
    dest.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" '
        'viewBox="0 0 1024 1024">\n'
        f'  <image width="1024" height="1024" href="data:image/png;base64,{b64}" />\n'
        '</svg>\n')
    print(f"  {dest.relative_to(ROOT)}  svg wrapping a {px}px png ({len(b64)//1024}KiB b64)")


def write_xpm(dest: Path, size: int = 64) -> None:
    # Hand-rolled so the disc keeps its silhouette: XPM has a transparent
    # colour, and quantizing a flattened tile would square the logo off.
    img = tile().resize((size, size), Image.LANCZOS)
    px = img.load()
    colors: dict[tuple[int, int, int], str] = {}
    chars = [c for c in (chr(n) for n in range(33, 127)) if c not in '"\\']
    grid = []
    for y in range(size):
        row = []
        for x in range(size):
            r, g, b, a = px[x, y]
            if a < 128:
                row.append(None)
                continue
            key = (r // 16 * 16, g // 16 * 16, b // 16 * 16)
            if key not in colors:
                colors[key] = chars[len(colors)]
            row.append(colors[key])
        grid.append(row)
    assert len(colors) <= len(chars), f"{len(colors)} colors do not fit one XPM char"
    lines = [f"{size} {size} {len(colors) + 1} 1", f"{chars[len(colors)]} c None"]
    lines += [f"{c} c #{r:02x}{g:02x}{b:02x}" for (r, g, b), c in colors.items()]
    lines += ["".join(c if c else chars[len(colors)] for c in row) for row in grid]
    dest.write_text("/* XPM */\nstatic char *code_xpm[] = {\n" + ",\n".join(f'"{l}"' for l in lines) + "\n};\n")
    print(f"  {dest.relative_to(ROOT)}  {size}x{size}, {len(colors)} colors + transparent")


def main() -> int:
    if not (ART / "crow-logo.png").exists():
        print(f"missing {ART / 'crow-logo.png'}", file=sys.stderr)
        return 1
    write_png(1024, RES / "linux/code.png")
    write_embedded_svg(RES / "linux/code.svg", 256)
    write_embedded_svg(ROOT / "vscodium/src/stable/src/vs/workbench/browser/media/code-icon.svg", 64)
    for quality in ("stable", "insider"):
        for name in ("codium_clt.svg", "codium_cnl.svg", "codium_cnl_w80_b8.svg"):
            target = ROOT / "vscodium" / "icons" / quality / name
            if target.parent.exists():
                write_embedded_svg(target, 256)
    write_xpm(RES / "linux/rpm/code.xpm")
    write_png(192, RES / "server/code-192.png")
    write_png(512, RES / "server/code-512.png")
    write_favicon(RES / "server/favicon.ico")
    return 0


if __name__ == "__main__":
    sys.exit(main())
