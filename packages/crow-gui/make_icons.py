#!/usr/bin/env python3
"""Regenerate crow's IDE icons from art/ into the vendored VSCodium tree.

VSCodium's own icons/build_icons.sh needs rsvg-convert/imagemagick/icns tools
and downloads VSCodium art from the network; crow builds Linux only, so this
script derives exactly the files the Linux build and the web server consume
from the committed brand art in art/. Run it after changing the art, then
commit both art/ and the generated files.
"""

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
ART = ROOT / "art"
RES = ROOT / "vscodium" / "src" / "stable" / "resources"
BG = "#6175ea"  # the brand tile background, matching art/crow-logo.png


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
    # its own background or it vanishes on light desktop themes.
    src = (ART / "crow-logo.svg").read_text()
    rect = f'  <rect width="1024" height="1024" fill="{BG}" />\n'
    marker = '<defs\n     id="defs1" />'
    assert marker in src, "unexpected art/crow-logo.svg shape"
    dest.write_text(src.replace(marker, marker + "\n" + rect, 1))
    print(f"  {dest.relative_to(ROOT)}  vector + {BG} background")


def write_xpm(dest: Path, size: int = 64, ncolors: int = 64) -> None:
    q = tile().resize((size, size), Image.LANCZOS).convert("RGB").quantize(colors=ncolors)
    used = sorted(idx for _, idx in q.getcolors(256))
    pal = q.getpalette()
    chars = [c for c in (chr(n) for n in range(32, 127)) if c not in '"\\']
    assert len(used) <= len(chars), f"{len(used)} colors do not fit one XPM char"
    ch = {idx: chars[k] for k, idx in enumerate(used)}
    px = q.load()
    lines = [f"{size} {size} {len(used)} 1"]
    lines += [f"{ch[i]} c #{pal[i * 3]:02x}{pal[i * 3 + 1]:02x}{pal[i * 3 + 2]:02x}" for i in used]
    lines += ["".join(ch[px[x, y]] for x in range(size)) for y in range(size)]
    dest.write_text("/* XPM */\nstatic char *code_xpm[] = {\n" + ",\n".join(f'"{l}"' for l in lines) + "\n};\n")
    print(f"  {dest.relative_to(ROOT)}  {size}x{size}, {len(used)} colors")


def main() -> int:
    if not (ART / "crow-logo.png").exists():
        print(f"missing {ART / 'crow-logo.png'}", file=sys.stderr)
        return 1
    write_png(1024, RES / "linux/code.png")
    write_svg(RES / "linux/code.svg")
    write_xpm(RES / "linux/rpm/code.xpm")
    write_png(192, RES / "server/code-192.png")
    write_png(512, RES / "server/code-512.png")
    write_favicon(RES / "server/favicon.ico")
    return 0


if __name__ == "__main__":
    sys.exit(main())
